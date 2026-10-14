"""Bounded, memory-only single-image OCR adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import io
import multiprocessing
from multiprocessing.connection import Connection
import os
import time
import warnings


class MediaError(Exception):
    """Safe error with no user media, OCR text, or decoder details."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ImageLimits:
    max_bytes: int = 3 * 1024 * 1024
    max_pixels: int = 8_000_000
    max_candidates: int = 32
    max_line_chars: int = 96
    deadline_seconds: float = 20.0
    startup_timeout_seconds: float = 120.0
    recycle_after_requests: int = 25
    min_glucose_mg_dl: int = int(os.environ.get("GLICO_MEDIA_MIN_GLUCOSE_MG_DL", "20"))
    max_glucose_mg_dl: int = int(os.environ.get("GLICO_MEDIA_MAX_GLUCOSE_MG_DL", "600"))
    min_confidence: float = float(os.environ.get("GLICO_MEDIA_MIN_OCR_CONFIDENCE", "0.75"))


@dataclass(frozen=True)
class TextCandidate:
    text: str
    confidence: float | None
    box: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class Extraction:
    candidates: tuple[TextCandidate, ...]
    engine: str
    elapsed_ms: int


def _decode_image(data: bytes, limits: ImageLimits):
    if not data or len(data) > limits.max_bytes:
        raise MediaError("payload_too_large" if data else "invalid_image")
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError

        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise MediaError("unsupported_media_type")
                if getattr(source, "n_frames", 1) != 1:
                    raise MediaError("unsupported_media_type")
                if source.width * source.height > limits.max_pixels:
                    raise MediaError("payload_too_large")
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGB")
                # Detach the returned pixels from source metadata and input buffer.
                return image.copy()
    except MediaError:
        raise
    except Exception as exc:
        # Do not expose decoder messages; callers must not log the original exception.
        raise MediaError("invalid_image") from None


def _run_paddle(connection: Connection, limits: ImageLimits, text_detection_model_dir: str,
                text_recognition_model_dir: str, max_rss_bytes: int) -> None:
    """Persistent isolated child with bounded request count and RSS recycling."""
    try:
        import numpy as np
        from pathlib import Path

        os.environ["PADDLE_PDX_MODEL_SOURCE"] = "LOCAL"
        from paddleocr import PaddleOCR
        if not Path(text_detection_model_dir).is_dir() or not Path(text_recognition_model_dir).is_dir():
            connection.send(("startup_error", "capability_unavailable"))
            return
        engine = PaddleOCR(lang="en", text_detection_model_name="PP-OCRv5_server_det",
            text_detection_model_dir=text_detection_model_dir, text_recognition_model_name="en_PP-OCRv5_mobile_rec",
            text_recognition_model_dir=text_recognition_model_dir, use_doc_orientation_classify=False,
            use_doc_unwarping=False, use_textline_orientation=False)
        connection.send(("ready",))
        requests = 0
        while True:
            message = connection.recv()
            if message[0] == "stop":
                return
            _, request_id, data = message
            try:
                image = _decode_image(data, limits)
                output = engine.predict(np.asarray(image))
                image.close()
                candidates = _normalize_paddle(output, limits)
                try:
                    import psutil
                    rss = psutil.Process().memory_info().rss
                except Exception:
                    rss = 0
                requests += 1
                recycle = requests >= limits.recycle_after_requests or (max_rss_bytes > 0 and rss > max_rss_bytes)
                connection.send(("ok", request_id, candidates, rss, recycle))
                if recycle:
                    return
            except MediaError as exc:
                connection.send(("error", request_id, exc.code, True))
                return
    except (ImportError, ModuleNotFoundError):
        try: connection.send(("startup_error", "capability_unavailable"))
        except Exception: pass
    except Exception:
        try: connection.send(("startup_error", "processing_failed"))
        except Exception: pass
    finally:
        try: connection.close()
        except Exception: pass


def _bounded_text(value: object, max_chars: int) -> str:
    # Keep only a single bounded line; no logs or persistence are performed here.
    text = " ".join(str(value).split())
    return text[:max_chars]


def _normalize_paddle(output: object, limits: ImageLimits) -> tuple[TextCandidate, ...]:
    candidates: list[TextCandidate] = []
    # PaddleOCR 3.x returns result objects with json/text fields; support the
    # documented rec_texts/rec_scores/dt_polys shape without returning raw objects.
    for result in output if isinstance(output, (list, tuple)) else [output]:
        payload = getattr(result, "json", None)
        if callable(payload):
            payload = payload()
        if isinstance(payload, dict):
            payload = payload.get("res", payload)
        if isinstance(payload, dict) and isinstance(payload.get("rec_texts"), (list, tuple)):
            texts = payload.get("rec_texts", [])
            scores = payload.get("rec_scores", [])
            boxes = payload.get("dt_polys", [])
            for index, raw_text in enumerate(texts):
                text = _bounded_text(raw_text, limits.max_line_chars)
                if not text:
                    continue
                confidence = _safe_confidence(scores[index] if index < len(scores) else None)
                box = _box_from_polygon(boxes[index]) if index < len(boxes) else None
                candidates.append(TextCandidate(text, confidence, box))
                if len(candidates) >= limits.max_candidates:
                    return tuple(candidates)
            continue
        # Handle PaddleOCR 2.x nested [box, (text, score)] results.
        for item in result if isinstance(result, (list, tuple)) else []:
            try:
                polygon, pair = item
                text = _bounded_text(pair[0], limits.max_line_chars)
                if text:
                    candidates.append(TextCandidate(text, _safe_confidence(pair[1]), _box_from_polygon(polygon)))
            except (TypeError, IndexError, ValueError):
                continue
            if len(candidates) >= limits.max_candidates:
                return tuple(candidates)
    return tuple(candidates)


def _safe_confidence(value: object) -> float | None:
    try:
        score = float(value)
        return score if 0 <= score <= 1 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _box_from_polygon(value: object) -> tuple[int, int, int, int] | None:
    try:
        points = [(int(point[0]), int(point[1])) for point in value]
        if not points:
            return None
        xs, ys = zip(*points)
        return min(xs), min(ys), max(xs), max(ys)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


class PaddleReadingExtractor:
    """Run PaddleOCR in a warmed isolated process with hard deadline and recycling.

    This adapter returns bounded OCR candidates only. It never selects or confirms
    a glucose value. The caller must require review and confirmation.
    """

    engine_version = "PaddleOCR 3.3.2 / PaddleX 3.3.13 / PP-OCRv5 server detection + English mobile recognition"

    def __init__(
        self,
        text_detection_model_dir: str | None = None,
        text_recognition_model_dir: str | None = None,
        limits: ImageLimits | None = None,
    ):
        self.limits = limits or ImageLimits()
        self.text_detection_model_dir = text_detection_model_dir
        self.text_recognition_model_dir = text_recognition_model_dir
        self.max_rss_bytes = int(os.environ.get("GLICO_MEDIA_MAX_RSS_BYTES", str(1536 * 1024 * 1024)))
        self._process = None
        self._connection = None
        self._lock = asyncio.Lock()
        self._request_id = 0

    async def _ensure_started(self) -> None:
        if not self.text_detection_model_dir or not self.text_recognition_model_dir:
            raise MediaError("capability_unavailable")
        if self._process is not None and self._process.is_alive() and self._connection is not None:
            return
        self._discard()
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=True)
        process = context.Process(target=_run_paddle, args=(child, self.limits, self.text_detection_model_dir,
            self.text_recognition_model_dir, self.max_rss_bytes), daemon=True)
        process.start()
        child.close()
        self._process, self._connection = process, parent
        deadline = time.monotonic() + self.limits.startup_timeout_seconds
        try:
            while not parent.poll():
                if not process.is_alive():
                    self._discard(); raise MediaError("capability_unavailable")
                if time.monotonic() >= deadline:
                    self._discard(); raise MediaError("processing_timeout")
                await asyncio.sleep(0.025)
            message = parent.recv()
            if message[0] != "ready":
                self._discard(); raise MediaError(message[1] if len(message) > 1 else "capability_unavailable")
        except asyncio.CancelledError:
            self._discard()
            raise

    def _discard(self) -> None:
        connection, process = self._connection, self._process
        self._connection = self._process = None
        if connection is not None:
            try: connection.close()
            except Exception: pass
        if process is not None:
            if process.is_alive(): process.terminate()
            process.join(timeout=1)
            if process.is_alive() and hasattr(process, "kill"):
                process.kill(); process.join(timeout=1)

    async def start_async(self) -> None:
        async with self._lock:
            await self._ensure_started()

    async def aclose(self) -> None:
        async with self._lock:
            if self._connection is not None and self._process is not None and self._process.is_alive():
                try: self._connection.send(("stop",))
                except Exception: pass
            self._discard()

    async def extract_async(self, data: bytes) -> Extraction:
        _decode_image(data, self.limits).close()
        started = time.monotonic()
        async with self._lock:
            await self._ensure_started()
            connection, process = self._connection, self._process
            self._request_id += 1
            request_id = self._request_id
            connection.send(("run", request_id, data))
            deadline = time.monotonic() + self.limits.deadline_seconds
            try:
                while not connection.poll():
                    if not process.is_alive(): raise MediaError("processing_failed")
                    if time.monotonic() >= deadline: raise MediaError("processing_timeout")
                    await asyncio.sleep(0.025)
                message = connection.recv()
                if message[0] == "error": raise MediaError(message[2])
                _, returned_id, candidates, _rss, recycle = message
                if returned_id != request_id: raise MediaError("processing_failed")
                result = Extraction(tuple(candidates), self.engine_version, int((time.monotonic() - started) * 1000))
                if recycle: self._discard()
                return result
            except asyncio.CancelledError:
                self._discard()
                raise
            except Exception:
                self._discard()
                raise

    def extract(self, data: bytes) -> Extraction:
        """Synchronous compatibility entry point for offline callers."""
        _decode_image(data, self.limits).close()
        if not self.text_detection_model_dir or not self.text_recognition_model_dir:
            raise MediaError("capability_unavailable")

        async def one_request() -> Extraction:
            try:
                return await self.extract_async(data)
            finally:
                await self.aclose()

        return asyncio.run(one_request())


WORKING_SIDE = 800


def _png(image) -> bytes:
    import io

    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def _open_rgb(data: bytes):
    import io
    from PIL import Image

    image = Image.open(io.BytesIO(data))
    image.load()
    return image.convert("RGB")


def prepare_for_ocr(data: bytes) -> bytes:
    """Downscale (never upscale) to a working size: faster, and the dotted LCD texture of meters
    stops confusing the recognizer (the same Accu-Chek photo goes from 0.70 to 0.83 confidence)."""
    try:
        from PIL import Image

        image = _open_rgb(data)
        if max(image.size) <= WORKING_SIDE:
            return data
        ratio = WORKING_SIDE / max(image.size)
        return _png(image.resize((max(1, int(image.width * ratio)), max(1, int(image.height * ratio))), Image.LANCZOS))
    except Exception:
        return data


def enhanced_variants(data: bytes) -> list[bytes]:
    """Other views of the same photo for a retry when the first pass does not conclude.

    Cheap, smaller scales first (a few seconds each); a light blur next because it can also merge
    digits ("106" -> "1106"); the original resolution last, since it can take 10 s or more. All
    in memory.
    """
    try:
        from PIL import Image, ImageFilter

        original = _open_rgb(data)
        if max(original.size) > 1280:
            ratio = 1280 / max(original.size)
            original = original.resize((max(1, int(original.width * ratio)), max(1, int(original.height * ratio))), Image.LANCZOS)
        working = original
        if max(working.size) > WORKING_SIDE:
            ratio = WORKING_SIDE / max(working.size)
            working = working.resize((max(1, int(working.width * ratio)), max(1, int(working.height * ratio))), Image.LANCZOS)
        radius = min(2.0, max(1.0, min(working.size) / 480))

        def scaled(factor):
            return working.resize((max(1, int(working.width * factor)), max(1, int(working.height * factor))), Image.LANCZOS)

        views = [scaled(0.6), scaled(0.45), working.filter(ImageFilter.GaussianBlur(radius))]
        if working is not original:
            views.append(original)
        return [_png(view) for view in views]
    except Exception:
        return []
