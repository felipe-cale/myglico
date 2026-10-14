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
    assessment = response.json()["assessment"]
    # The speaker did not say the unit; a glucose context makes mg/dL the inferred default.
    assert assessment["needs_clarification"] is False
    assert assessment["candidate_value_mg_dl"] == 128
    assert assessment["candidate_unit"] == "mg/dL" and assessment["unit_inferred"] is True


@pytest.mark.parametrize("language,spoken", [
    ("pt", "minha glicose está em cento e vinte miligramas por decilitro"),
    ("pt", "um dois zero miligramas por decilitro"),
    ("en", "my glucose is one hundred twenty milligrams per deciliter"),
    ("en", "one two zero milligrams per deciliter"),
    ("es", "mi glucosa es ciento veinte miligramos por decilitro"),
    ("es", "uno dos cero miligramos por decilitro"),
])
def test_spoken_numbers_and_units_reach_the_gate_as_digits(language, spoken):
    class Spoken:
        limits = AudioLimits()

        async def transcribe_async(self, data):
            return Transcription(spoken, language, 4, "fake-test-only", 0.95)

    body = wav_bytes()
    timestamp = str(int(time.time()))
    signed = sign_request(b"w" * 32, "POST", "/internal/extract/audio", timestamp, "D" * 24, body)
    headers = {
        "content-type": "application/octet-stream", "x-correlation-id": "syntheticCorrelation123",
        "x-worker-timestamp": signed.timestamp, "x-worker-nonce": signed.nonce,
        "x-worker-content-sha256": signed.body_sha256, "x-worker-signature": signed.signature,
    }
    client = TestClient(create_media_app(b"w" * 32, ReplayStore(), transcriber=Spoken()))
    response = client.post("/internal/extract/audio", content=body, headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert "120 mg/dL" in payload["text"]
    assessment = payload["assessment"]
    assert assessment["candidate_value_mg_dl"] == 120
    assert assessment["needs_clarification"] is False


def _spoken_assessment(spoken, language="pt", confidence=0.95):
    class Spoken:
        limits = AudioLimits()

        async def transcribe_async(self, data):
            return Transcription(spoken, language, 4, "fake-test-only", confidence)

    body = wav_bytes()
    signed = sign_request(b"w" * 32, "POST", "/internal/extract/audio", str(int(time.time())), "E" * 24, body)
    headers = {
        "content-type": "application/octet-stream", "x-correlation-id": "syntheticCorrelation123",
        "x-worker-timestamp": signed.timestamp, "x-worker-nonce": signed.nonce,
        "x-worker-content-sha256": signed.body_sha256, "x-worker-signature": signed.signature,
    }
    client = TestClient(create_media_app(b"w" * 32, ReplayStore(), transcriber=Spoken()))
    response = client.post("/internal/extract/audio", content=body, headers=headers)
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("spoken,language,mg_dl,unit,inferred", [
    ("minha glicose deu cento e vinte", "pt", 120, "mg/dL", True),
    ("my glucose is one hundred twenty", "en", 120, "mg/dL", True),
    ("mi glucosa es ciento veinte", "es", 120, "mg/dL", True),
    ("minha glicose deu cinco vírgula seis", "pt", 100.9, "mmol/L", True),
    ("my glucose is five point six", "en", 100.9, "mmol/L", True),
    ("minha glicose deu 5,6 mmol/L", "pt", 100.9, "mmol/L", False),
    ("minha glicose deu 120 mg/dL", "pt", 120, "mg/dL", False),
])
def test_unit_is_inferred_only_when_the_speaker_omits_it(spoken, language, mg_dl, unit, inferred):
    assessment = _spoken_assessment(spoken, language)["assessment"]
    assert assessment["needs_clarification"] is False, assessment
    assert assessment["candidate_value_mg_dl"] == mg_dl
    assert assessment["candidate_unit"] == unit and assessment["unit_inferred"] is inferred


@pytest.mark.parametrize("spoken", [
    "amanhã às 9 horas vou ao mercado",           # a number with no glucose context is never a reading
    "minha glicose foi 120 e depois 140",          # two values stay ambiguous
    "minha glicose deu 700",                       # out of the physiological range
])
def test_unrelated_ambiguous_or_out_of_range_speech_still_needs_clarification(spoken):
    assessment = _spoken_assessment(spoken)["assessment"]
    assert assessment["needs_clarification"] is True
    assert assessment["candidate_value_mg_dl"] is None


@pytest.mark.parametrize("header,expected", [("pt", "pt"), ("EN", "en"), ("es", "es"), ("fr", None), ("", None)])
def test_language_hint_header_reaches_the_engine_only_when_allowed(header, expected):
    seen = {}

    class Hinted:
        limits = AudioLimits()

        async def transcribe_async(self, data, language=None):
            seen["language"] = language
            return Transcription("minha glicose 120 mg/dL", "pt", 4, "fake-test-only", 0.95)

    body = wav_bytes()
    signed = sign_request(b"w" * 32, "POST", "/internal/extract/audio", str(int(time.time())), "F" * 24, body)
    headers = {
        "content-type": "application/octet-stream", "x-correlation-id": "syntheticCorrelation123",
        "x-worker-timestamp": signed.timestamp, "x-worker-nonce": signed.nonce,
        "x-worker-content-sha256": signed.body_sha256, "x-worker-signature": signed.signature,
        "x-glico-language": header,
    }
    client = TestClient(create_media_app(b"w" * 32, ReplayStore(), transcriber=Hinted()))
    assert client.post("/internal/extract/audio", content=body, headers=headers).status_code == 200
    assert seen["language"] == expected
