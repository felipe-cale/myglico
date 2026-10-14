"""Private ASGI boundary for the media worker: HMAC-authenticated, memory-only photo OCR and audio ASR.

This module is only the HTTP layer. The decisions live elsewhere: ``reading`` (transcript -> reading),
``spoken`` (numbers and units in text), ``photo`` (photo pipeline), ``devcapture`` (dev-only capture).
"""

from __future__ import annotations

import re
import asyncio
import inspect
import time
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.media_worker.auth import ReplayStore, WorkerSignature, verify_request
from app.media_worker.audio import AudioLimits, FasterWhisperTranscriber
from app.media_worker import devcapture
from app.media_worker.image import ImageLimits, MediaError, PaddleReadingExtractor
from app.media_worker.photo import read_photo
from app.media_worker.reading import assess_transcript


_CORRELATION_RE = re.compile(r"^[A-Za-z0-9_-]{16,80}$")


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
            saved_image = devcapture.save_image(body)
            started_image = time.monotonic()
            result, assessment, tried = await read_photo(engine, body)
        except MediaError as exc:
            status = 504 if exc.code == "processing_timeout" else 503 if exc.code == "capability_unavailable" else 422
            raise HTTPException(status_code=status, detail={"code": exc.code}) from None
        finally:
            # Drop this reference before returning; buffers are never logged or persisted.
            del body
            chunks.clear()
            slots.release()
        devcapture.note(saved_image, {
            "assessment": assessment, "passes": len(tried), "total_seconds": round(time.monotonic() - started_image, 1),
            "candidates": [{"text": item.text, "confidence": item.confidence, "box": item.box} for item in result.candidates],
            "expected": "(preencher: o valor que o visor mostrava)"})
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
            saved_audio = devcapture.save_audio(body)
        except MediaError as exc:
            status = 504 if exc.code == "processing_timeout" else 503 if exc.code == "capability_unavailable" else 422
            raise HTTPException(status_code=status, detail={"code": exc.code}) from None
        finally:
            del body
            chunks.clear()
            slots.release()
        # Spelled-out numbers and units ("cento e vinte", "um dois zero", "miligramas por
        # decilitro") become digits and mg/dL; the strict digit-and-unit gate still decides.
        spoken_text, assessment = assess_transcript(
            result.text, result.language, getattr(result, "confidence", None),
            getattr(result, "digit_confidence", None), speech_engine.limits)
        confidence = getattr(result, "confidence", None)
        devcapture.note(saved_audio, {
            "transcript": spoken_text, "raw_transcript": result.text, "language": result.language,
            "language_hint": hint, "confidence": getattr(result, "confidence", None),
            "digit_confidence": getattr(result, "digit_confidence", None), "assessment": assessment,
            "elapsed_ms": result.elapsed_ms, "engine": result.engine,
            "expected": "(preencher: o que foi dito)"})
        return JSONResponse(
            {"correlation_id": correlation_id, "engine": result.engine, "elapsed_ms": result.elapsed_ms,
             "language": result.language, "text": spoken_text, "confidence": confidence,
             "assessment": assessment},
            headers={"Cache-Control": "no-store"},
        )

    return app
