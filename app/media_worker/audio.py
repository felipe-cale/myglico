"""Bounded, memory-only multilingual speech recognition adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import io
import multiprocessing
import os
from pathlib import Path
import time

from app.media_worker.image import MediaError


@dataclass(frozen=True)
class AudioLimits:
    max_bytes: int = 3 * 1024 * 1024
    max_seconds: float = 60.0
    deadline_seconds: float = 45.0
    max_text_chars: int = 4000
    min_speech_seconds: float = 0.35
    allowed_languages: tuple[str, ...] = ("pt", "en", "es")
    startup_timeout_seconds: float = 120.0
    recycle_after_requests: int = 25
    min_glucose_mg_dl: int = int(os.environ.get("GLICO_MEDIA_MIN_GLUCOSE_MG_DL", "20"))
    max_glucose_mg_dl: int = int(os.environ.get("GLICO_MEDIA_MAX_GLUCOSE_MG_DL", "600"))
    min_confidence: float = float(os.environ.get("GLICO_MEDIA_MIN_ASR_CONFIDENCE", "0.5"))


@dataclass(frozen=True)
class Transcription:
    text: str
    language: str
    elapsed_ms: int
    engine: str
    confidence: float | None = None
    # Lowest word probability among the tokens that contain digits: how sure the model is of the
    # number itself, which matters more than the other words of a short sentence.
    digit_confidence: float | None = None


def wrong_language_suspected(sentence_marks: list[float], digit_marks: list[float]) -> bool:
    """Is the result with the interface language's hint so poor that the speaker may be using another one?

    Informal speech has a low average confidence even when the number was understood, so a confident
    digit token means the language was right. Re-running costs ~10 s (automatic language detection), so
    it is only for results that are bad overall or that found no number at all.
    """
    if not sentence_marks:
        return False
    average = sum(sentence_marks) / len(sentence_marks)
    if any(mark >= 0.5 for mark in digit_marks):
        return False
    return average < 0.25 or (average < 0.45 and not digit_marks)


def _decode_audio(data: bytes, limits: AudioLimits):
    if not data or len(data) > limits.max_bytes:
        raise MediaError("payload_too_large" if data else "invalid_audio")
    try:
        import av
        import numpy as np

        with av.open(io.BytesIO(data), mode="r") as container:
            formats = set(container.format.name.split(","))
            if not formats.intersection({"wav", "matroska", "webm", "ogg", "mov", "mp4"}):
                raise MediaError("unsupported_media_type")
            streams = [stream for stream in container.streams if stream.type == "audio"]
            if len(streams) != 1:
                raise MediaError("unsupported_media_type")
            stream = streams[0]
            if stream.duration is not None and stream.time_base is not None:
                duration = float(stream.duration * stream.time_base)
                if duration > limits.max_seconds:
                    raise MediaError("payload_too_large")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            chunks = []
            samples = 0
            for frame in container.decode(stream):
                for output in resampler.resample(frame):
                    samples += output.samples
                    if samples > limits.max_seconds * 16000:
                        raise MediaError("payload_too_large")
                    chunks.append(output.to_ndarray().reshape(-1))
        if not chunks:
            raise MediaError("invalid_audio")
        audio = np.concatenate(chunks).astype(np.float32) / 32768.0
        if len(audio) / 16000 > limits.max_seconds:
            raise MediaError("payload_too_large")
        # Reject silence before ASR; no truncation or synthetic text.
        if float(np.sqrt(np.mean(audio * audio))) < 0.003:
            raise MediaError("speech_not_detected")
        return audio
    except MediaError:
        raise
    except Exception:
        raise MediaError("invalid_audio") from None


def _run_whisper(connection, limits: AudioLimits, model_dir: str, max_rss_bytes: int) -> None:
    try:
        from pathlib import Path
        from faster_whisper import WhisperModel
        if not Path(model_dir).is_dir():
            connection.send(("startup_error", "capability_unavailable")); return
        model = WhisperModel(model_dir, device="cpu", compute_type="int8", local_files_only=True)
        connection.send(("ready",))
        requests = 0
        while True:
            message = connection.recv()
            if message[0] == "stop": return
            request_id, audio = message[1], message[2]
            hint = message[3] if len(message) > 3 else None
            try:
                # The parent already decoded and validated the media once; the child only re-checks
                # that what arrived is a bounded mono waveform (defence in depth), it does not decode again.
                if getattr(audio, "ndim", 0) != 1 or len(audio) > int(limits.max_seconds * 16000):
                    connection.send(("error", request_id, "invalid_audio", False)); continue

                def transcribe_once(forced):
                    import math
                    segments, info = model.transcribe(audio, beam_size=1, vad_filter=True, language=forced,
                                                      word_timestamps=True)
                    found, marks, seconds, digit_marks = [], [], 0.0, []
                    for segment in segments:
                        segment_text = " ".join(str(segment.text).split())
                        if segment_text:
                            found.append(segment_text)
                            seconds += max(0.0, float(segment.end) - float(segment.start))
                            try:
                                marks.append(max(0.0, min(1.0, math.exp(float(segment.avg_logprob)))))
                            except Exception: pass
                            for word in (getattr(segment, "words", None) or []):
                                if any(ch.isdigit() for ch in str(word.word)):
                                    try: digit_marks.append(float(word.probability))
                                    except Exception: pass
                        if sum(map(len, found)) > limits.max_text_chars:
                            return None
                    return str(info.language), found, marks, seconds, digit_marks

                # The interface language skips Whisper's ~5 s language detection. If the result is
                # unsure (someone spoke another language), run once more with automatic detection.
                first = transcribe_once(hint if hint in limits.allowed_languages else None)
                if first is not None and hint in limits.allowed_languages and wrong_language_suspected(first[2], first[4]):
                    first = transcribe_once(None)
                if first is None:
                    connection.send(("error", request_id, "transcript_too_long", True)); return
                language, text_parts, scores, speech_seconds, digit_marks = first
                if language not in limits.allowed_languages:
                    connection.send(("error", request_id, "language_not_supported", True)); return
                text = " ".join(text_parts).strip()
                if not text or speech_seconds < limits.min_speech_seconds:
                    connection.send(("error", request_id, "speech_not_detected", False)); continue
                confidence = sum(scores) / len(scores) if scores else None
                try:
                    import psutil
                    rss = psutil.Process().memory_info().rss
                except Exception: rss = 0
                requests += 1
                recycle = requests >= limits.recycle_after_requests or (max_rss_bytes > 0 and rss > max_rss_bytes)
                digit_confidence = min(digit_marks) if digit_marks else None
                connection.send(("ok", request_id, text, language, confidence, recycle, digit_confidence))
                if recycle: return
            except MediaError as exc:
                connection.send(("error", request_id, exc.code, False))
    except (ImportError, ModuleNotFoundError):
        try: connection.send(("startup_error", "capability_unavailable"))
        except Exception: pass
    except Exception:
        try: connection.send(("startup_error", "processing_failed"))
        except Exception: pass
    finally:
        try: connection.close()
        except Exception: pass


class FasterWhisperTranscriber:
    """Run local multilingual Whisper in a warmed, recycled isolated child."""

    def __init__(self, model_dir: str | None = None, limits: AudioLimits | None = None):
        self.model_dir = model_dir
        self.limits = limits or AudioLimits()
        self.engine_version = "faster-whisper local multilingual int8"
        self.max_rss_bytes = int(os.environ.get("GLICO_MEDIA_MAX_RSS_BYTES", str(1536 * 1024 * 1024)))
        self._process = None
        self._connection = None
        self._lock = asyncio.Lock()
        self._request_id = 0

    async def _ensure_started(self) -> None:
        if not self.model_dir or not Path(self.model_dir).is_dir(): raise MediaError("capability_unavailable")
        if self._process is not None and self._process.is_alive() and self._connection is not None: return
        self._discard()
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=True)
        process = context.Process(target=_run_whisper, args=(child, self.limits, self.model_dir, self.max_rss_bytes), daemon=True)
        process.start(); child.close()
        self._process, self._connection = process, parent
        deadline = time.monotonic() + self.limits.startup_timeout_seconds
        try:
            while not parent.poll():
                if not process.is_alive(): self._discard(); raise MediaError("capability_unavailable")
                if time.monotonic() >= deadline: self._discard(); raise MediaError("processing_timeout")
                await asyncio.sleep(0.025)
            message = parent.recv()
            if message[0] != "ready": self._discard(); raise MediaError(message[1])
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
            if process.is_alive(): process.kill(); process.join(timeout=1)

    async def start_async(self) -> None:
        async with self._lock: await self._ensure_started()

    async def aclose(self) -> None:
        async with self._lock:
            if self._connection is not None and self._process is not None and self._process.is_alive():
                try: self._connection.send(("stop",))
                except Exception: pass
            self._discard()

    async def transcribe_async(self, data: bytes, language: str | None = None) -> Transcription:
        # Decode and validate once, here, before the model process is involved; the waveform is sent as is.
        audio = _decode_audio(data, self.limits)
        started = time.monotonic()
        async with self._lock:
            await self._ensure_started()
            connection, process = self._connection, self._process
            self._request_id += 1
            request_id = self._request_id
            connection.send(("run", request_id, audio, language))
            deadline = time.monotonic() + self.limits.deadline_seconds
            try:
                while not connection.poll():
                    if not process.is_alive(): raise MediaError("processing_failed")
                    if time.monotonic() >= deadline: raise MediaError("processing_timeout")
                    await asyncio.sleep(0.025)
                message = connection.recv()
                if message[0] == "error":
                    code = message[2]
                    if message[3]: self._discard()
                    raise MediaError(code)
                _, returned_id, text, language, confidence, recycle = message[:6]
                digit_confidence = message[6] if len(message) > 6 else None
                if returned_id != request_id: raise MediaError("processing_failed")
                result = Transcription(text, language, int((time.monotonic() - started) * 1000), self.engine_version, confidence,
                                       digit_confidence)
                if recycle: self._discard()
                return result
            except asyncio.CancelledError:
                self._discard(); raise
            except Exception:
                self._discard(); raise
