"""Private ASGI boundary for memory-only, authenticated single-image OCR."""

from __future__ import annotations

import re
import asyncio
import inspect
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.media_worker.auth import ReplayStore, WorkerSignature, verify_request
from app.media_worker.audio import AudioLimits, FasterWhisperTranscriber
from app.media_worker.image import ImageLimits, MediaError, PaddleReadingExtractor
from app.media_worker.spoken import normalize_spoken


_CORRELATION_RE = re.compile(r"^[A-Za-z0-9_-]{16,80}$")
_UNIT_RE = re.compile(r"\b(?:mg\s*/?\s*d[l1]|miligramos?\s+por\s+decilitro)\b", re.I)


def _assessment(candidates: list[int], unit_present: bool, confidence: float | None, limits) -> dict:
    reasons = []
    unique = list(dict.fromkeys(candidates))
    if not unit_present: reasons.append("unit_missing")
    if len(unique) != 1: reasons.append("multiple_candidates" if unique else "value_not_detected")
    value = unique[0] if len(unique) == 1 else None
    if value is not None and not limits.min_glucose_mg_dl <= value <= limits.max_glucose_mg_dl:
        reasons.append("value_out_of_range")
    if confidence is None:
        reasons.append("confidence_unavailable")
    elif confidence < limits.min_confidence:
        reasons.append("confidence_below_threshold")
    clear = not reasons
    return {
        "status": "review_required" if clear else "needs_clarification",
        "needs_clarification": not clear,
        "clarification_reasons": reasons,
        "candidate_value_mg_dl": value if clear else None,
        "candidate_confidence": confidence,
        "physiological_range_mg_dl": [limits.min_glucose_mg_dl, limits.max_glucose_mg_dl],
        "confidence_threshold": limits.min_confidence,
    }


_MMOL_RE = re.compile(r"\bmmol\s*/?\s*l\b", re.I)
# Without a spoken unit the number is only read as a glucose when the speech is about a measurement.
_GLUCOSE_CONTEXT = re.compile(
    r"gli[cs]|gluc|a[cç]úcar|azúcar|sugar|diabet|medi[çc]|medic[ií]|medid|measur|resultado|result"
    r"|marcou|deu |mostrou|show|reading|lectura|leitura|lectur", re.I)


def _audio_reading(text: str) -> dict | None:
    """Single number in the transcript -> value in mg/dL with the unit explicit or inferred.

    Speakers rarely say the unit. Decimals and values under 20 are read as mmol/L, 34+ as mg/dL, the
    ambiguous 20-33 band as mg/dL (Brazilian default). The review card always shows the unit.
    """
    numbers = list(dict.fromkeys(re.findall(r"(?<![\d.,])(\d{1,4}(?:[.,]\d{1,2})?)(?!\d)", text)))
    if len(numbers) != 1:
        return None
    raw = numbers[0]
    value = float(raw.replace(",", "."))
    decimal = "." in raw or "," in raw
    if _MMOL_RE.search(text):
        unit, inferred = "mmol/L", False
    elif _UNIT_RE.search(text):
        unit, inferred = "mg/dL", False
    elif _GLUCOSE_CONTEXT.search(text):
        unit, inferred = ("mmol/L" if (decimal or value < 20) else "mg/dL"), True
    else:
        return None
    mg_dl = round(value * 18.0182, 1) if unit == "mmol/L" else value
    return {"original_value": value, "unit": unit, "inferred": inferred, "mg_dl": mg_dl}


def _audio_numeric_candidates(text: str) -> list[int]:
    """Return only explicit digit tokens; spoken number words remain untrusted."""
    return [int(raw) for raw in re.findall(r"(?<!\d)\d{2,4}(?!\d)", text)]


class AsyncExtractor(Protocol):
    limits: ImageLimits

    async def extract_async(self, data: bytes): ...


class AsyncTranscriber(Protocol):
    limits: AudioLimits

    async def transcribe_async(self, data: bytes): ...


def create_media_app(
    secret: bytes,
    replay_store: ReplayStore,
    extractor: AsyncExtractor | None = None,
    *,
    transcriber: AsyncTranscriber | None = None,
    max_inflight: int = 1,
) -> FastAPI:
    """Create a private app; caller must bind it only to the internal network."""
    if len(secret) < 32:
        raise ValueError("worker secret must contain at least 32 bytes")
    engine = extractor or PaddleReadingExtractor()
    speech_engine = transcriber or FasterWhisperTranscriber()
    if max_inflight < 1:
        raise ValueError("max_inflight must be positive")
    slots = asyncio.Semaphore(max_inflight)
    @asynccontextmanager
    async def lifespan(_app):
        for component in (engine, speech_engine):
            starter = getattr(component, "start_async", None)
            if starter is not None:
                try:
                    await starter()
                except MediaError as exc:
                    if exc.code != "capability_unavailable":
                        raise
        try:
            yield
        finally:
            for component in (engine, speech_engine):
                closer = getattr(component, "aclose", None)
                if closer is not None:
                    await closer()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.post("/internal/extract/image")
    async def extract_image(request: Request):
        media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/octet-stream":
            raise HTTPException(status_code=415, detail={"code": "unsupported_media_type"})
        correlation_id = request.headers.get("x-correlation-id", "")
        if not _CORRELATION_RE.fullmatch(correlation_id):
            raise HTTPException(status_code=400, detail={"code": "invalid_request"})

        # Per-process memory bound; account/global quotas must be reserved by gateway.
        if slots.locked():
            raise HTTPException(status_code=429, detail={"code": "worker_busy"})
        await slots.acquire()

        chunks: list[bytes] = []
        body = b""
        try:
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > engine.limits.max_bytes:
                    raise HTTPException(status_code=413, detail={"code": "payload_too_large"})
                chunks.append(chunk)
            body = b"".join(chunks)
            if not body:
                raise HTTPException(status_code=422, detail={"code": "invalid_image"})
            headers = WorkerSignature(
                timestamp=request.headers.get("x-worker-timestamp", ""),
                nonce=request.headers.get("x-worker-nonce", ""),
                body_sha256=request.headers.get("x-worker-content-sha256", ""),
                signature=request.headers.get("x-worker-signature", ""),
            )
            if not verify_request(
                secret, request.method, request.url.path, body, headers, replay_store,
                max_skew_seconds=30,
            ):
                raise HTTPException(status_code=401, detail={"code": "worker_authentication_failed"})
            result = await engine.extract_async(body)
        except MediaError as exc:
            status = 504 if exc.code == "processing_timeout" else 503 if exc.code == "capability_unavailable" else 422
            raise HTTPException(status_code=status, detail={"code": exc.code}) from None
        finally:
            # Drop this reference before returning; buffers are never logged or persisted.
            del body
            chunks.clear()
            slots.release()
        texts = [item.text for item in result.candidates[: engine.limits.max_candidates]]
        # Only digit-only display lines qualify as candidate readings; separators
        # are excluded so dates and clock strings are not treated as glucose.
        readings = []
        for item in result.candidates:
            if re.fullmatch(r"\s*\d{2,4}\s*", item.text):
                height = (item.box[3] - item.box[1]) if item.box else 0
                readings.append((int(item.text.strip()), item.confidence, height))
        in_range = [r for r in readings
                    if engine.limits.min_glucose_mg_dl <= r[0] <= engine.limits.max_glucose_mg_dl]
        # Meters print the result in the largest digits; with several plausible
        # numbers (time, date, memory slot) take the clearly tallest one.
        chosen = in_range
        if len(in_range) > 1:
            ranked = sorted(in_range, key=lambda r: r[2], reverse=True)
            if ranked[0][2] > 0 and ranked[0][2] >= 1.25 * ranked[1][2]:
                chosen = [ranked[0]]
        numeric = [r[0] for r in chosen] if chosen else [r[0] for r in readings]
        numeric_confidence = [r[1] for r in (chosen or readings) if r[1] is not None]
        confidence = min(numeric_confidence) if numeric_confidence else None
        # A missing unit is assumed mg/dL: the proposal is still reviewed and
        # editable by the user before anything is written.
        assessment = _assessment(numeric, True, confidence, engine.limits)
        return JSONResponse(
            {
                "correlation_id": correlation_id,
                "engine": result.engine,
                "elapsed_ms": result.elapsed_ms,
                "candidates": [
                    {"text": item.text, "confidence": item.confidence, "box": item.box}
                    for item in result.candidates[: engine.limits.max_candidates]
                ],
                "assessment": assessment,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/internal/extract/audio")
    async def extract_audio(request: Request):
        media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/octet-stream":
            raise HTTPException(status_code=415, detail={"code": "unsupported_media_type"})
        correlation_id = request.headers.get("x-correlation-id", "")
        if not _CORRELATION_RE.fullmatch(correlation_id):
            raise HTTPException(status_code=400, detail={"code": "invalid_request"})
        if slots.locked():
            raise HTTPException(status_code=429, detail={"code": "worker_busy"})
        await slots.acquire()
        chunks: list[bytes] = []
        body = b""
        try:
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > speech_engine.limits.max_bytes:
                    raise HTTPException(status_code=413, detail={"code": "payload_too_large"})
                chunks.append(chunk)
            body = b"".join(chunks)
            if not body:
                raise HTTPException(status_code=422, detail={"code": "invalid_audio"})
            headers = WorkerSignature(
                timestamp=request.headers.get("x-worker-timestamp", ""),
                nonce=request.headers.get("x-worker-nonce", ""),
                body_sha256=request.headers.get("x-worker-content-sha256", ""),
                signature=request.headers.get("x-worker-signature", ""),
            )
            if not verify_request(secret, request.method, request.url.path, body, headers, replay_store, max_skew_seconds=30):
                raise HTTPException(status_code=401, detail={"code": "worker_authentication_failed"})
            hint = request.headers.get("x-glico-language", "").strip().lower()
            hint = hint if hint in {"pt", "en", "es"} else None
            if hint and "language" in inspect.signature(speech_engine.transcribe_async).parameters:
                result = await speech_engine.transcribe_async(body, language=hint)
            else:
                result = await speech_engine.transcribe_async(body)
        except MediaError as exc:
            status = 504 if exc.code == "processing_timeout" else 503 if exc.code == "capability_unavailable" else 422
            raise HTTPException(status_code=status, detail={"code": exc.code}) from None
        finally:
            del body
            chunks.clear()
            slots.release()
        # Spelled-out numbers and units ("cento e vinte", "um dois zero", "miligramas por
        # decilitro") become digits and mg/dL; the strict digit-and-unit gate still decides.
        spoken_text = normalize_spoken(result.text, result.language)
        reading = _audio_reading(spoken_text)
        confidence = getattr(result, "confidence", None)
        if reading is not None:
            assessment = _assessment([reading["mg_dl"]], True, confidence, speech_engine.limits)
            assessment.update(candidate_original_value=reading["original_value"],
                              candidate_unit=reading["unit"], unit_inferred=reading["inferred"])
        else:
            assessment = _assessment(_audio_numeric_candidates(spoken_text),
                                     bool(_UNIT_RE.search(spoken_text)), confidence, speech_engine.limits)
        return JSONResponse(
            {"correlation_id": correlation_id, "engine": result.engine, "elapsed_ms": result.elapsed_ms,
             "language": result.language, "text": spoken_text, "confidence": confidence,
             "assessment": assessment},
            headers={"Cache-Control": "no-store"},
        )

    return app
