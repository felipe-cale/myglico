import io
import time
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.media_worker.audio import AudioLimits, Transcription, _decode_audio
from app.media_worker.auth import sign_request
from app.media_worker.image import MediaError
from app.media_worker.service import create_media_app


def wav_bytes(seconds=1, amplitude=0.2):
    samples = (np.sin(np.arange(int(16000 * seconds)) * (2 * np.pi * 440 / 16000)) * amplitude * 32767).astype("<i2")
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(samples.tobytes())
    return stream.getvalue()


def test_audio_decode_enforces_duration_and_silence_in_memory():
    audio = _decode_audio(wav_bytes(), AudioLimits())
    assert len(audio) == 16000
    with pytest.raises(MediaError, match="payload_too_large"):
        _decode_audio(wav_bytes(2), AudioLimits(max_seconds=1))
    with pytest.raises(MediaError, match="speech_not_detected"):
        _decode_audio(wav_bytes(amplitude=0), AudioLimits())


class ReplayStore:
    def __init__(self):
        self.used = set()

    def consume_once(self, nonce, expires_at):
        if nonce in self.used:
            return False
        self.used.add(nonce)
        return True


class FakeTranscriber:
    limits = AudioLimits()

    async def transcribe_async(self, data):
        assert data.startswith(b"RIFF")
        return Transcription("Lectura 128", "pt", 4, "fake-test-only", 0.9)


def test_authenticated_audio_endpoint_returns_temporary_transcription():
    body = wav_bytes()
    timestamp = str(int(time.time()))
    signed = sign_request(b"w" * 32, "POST", "/internal/extract/audio", timestamp, "C" * 24, body)
    headers = {
        "content-type": "application/octet-stream",
        "x-correlation-id": "syntheticCorrelation123",
        "x-worker-timestamp": signed.timestamp,
        "x-worker-nonce": signed.nonce,
        "x-worker-content-sha256": signed.body_sha256,
        "x-worker-signature": signed.signature,
    }
    client = TestClient(create_media_app(b"w" * 32, ReplayStore(), transcriber=FakeTranscriber()))
    response = client.post("/internal/extract/audio", content=body, headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["language"] == "pt"
    assert response.json()["text"] == "Lectura 128"
    assert response.json()["assessment"]["needs_clarification"] is True
    assert "unit_missing" in response.json()["assessment"]["clarification_reasons"]
