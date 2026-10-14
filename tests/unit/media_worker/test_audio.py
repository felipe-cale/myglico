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


@pytest.mark.parametrize("spoken,mg_dl,unit", [
    ("Fiz o teste de 53.", 53, "mg/dL"),
    ("53", 53, "mg/dL"),
    ("35", 35, "mg/dL"),
    ("Minha iglesia me está 80.", 80, "mg/dL"),   # Whisper misheard "glicemia"; still one plausible number
    ("deu 5,6", 100.9, "mmol/L"),
])
def test_short_phrase_with_one_plausible_number_is_a_reading_with_inferred_unit(spoken, mg_dl, unit):
    assessment = _spoken_assessment(spoken)["assessment"]
    assert assessment["needs_clarification"] is False, assessment
    assert assessment["candidate_value_mg_dl"] == mg_dl
    assert assessment["candidate_unit"] == unit and assessment["unit_inferred"] is True


@pytest.mark.parametrize("spoken", [
    "faz 30 dias",
    "reunião às 8",
    "voltei às 10 horas",
    "daqui a 45 minutos",
    "são 14:30",
    "tenho 2 consultas",
    "foi há 3 meses",
    "one hundred and eighty people came to the meeting yesterday afternoon",
])
def test_times_durations_and_long_sentences_never_become_a_reading(spoken):
    assessment = _spoken_assessment(spoken)["assessment"]
    assert assessment["needs_clarification"] is True


@pytest.mark.parametrize("overall,digits,clear,low", [
    (0.30, 0.92, True, False),   # garbled words around a number the model is sure of
    (0.95, 0.30, True, True),    # unsure about the number: still proposed, flagged for a check
    (0.40, None, True, True),    # number came as words: only the overall confidence is available
    (0.95, 0.10, False, False),  # too unsure to even propose
])
def test_the_numbers_own_confidence_decides_when_it_is_known(overall, digits, clear, low):
    class Fuzzy:
        limits = AudioLimits()

        async def transcribe_async(self, data, language=None):
            return Transcription("Fisidate e Deus 75.", "pt", 4, "fake-test-only", overall, digits)

    body = wav_bytes()
    signed = sign_request(b"w" * 32, "POST", "/internal/extract/audio", str(int(time.time())), "K" * 24, body)
    headers = {
        "content-type": "application/octet-stream", "x-correlation-id": "syntheticCorrelation123",
        "x-worker-timestamp": signed.timestamp, "x-worker-nonce": signed.nonce,
        "x-worker-content-sha256": signed.body_sha256, "x-worker-signature": signed.signature,
    }
    client = TestClient(create_media_app(b"w" * 32, ReplayStore(), transcriber=Fuzzy()))
    assessment = client.post("/internal/extract/audio", content=body, headers=headers).json()["assessment"]
    assert (assessment["needs_clarification"] is False) is clear, assessment
    if clear:
        assert assessment["candidate_value_mg_dl"] == 75
        assert (assessment.get("low_confidence") is True) is low


def _opus_in_ogg(seconds=1):
    import av
    import numpy as np

    buffer = io.BytesIO()
    with av.open(buffer, mode="w", format="ogg") as container:
        stream = container.add_stream("libopus", rate=48000)
        stream.layout = "mono"
        samples = (np.sin(np.arange(48000 * seconds) * (2 * np.pi * 440 / 48000)) * 0.2 * 32767).astype("<i2")
        frame_size = 960
        for start in range(0, len(samples) - frame_size + 1, frame_size):
            frame = av.AudioFrame.from_ndarray(samples[start:start + frame_size].reshape(1, -1), format="s16", layout="mono")
            frame.sample_rate = 48000
            frame.pts = start
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return buffer.getvalue()


def test_ogg_opus_recordings_such_as_whatsapp_voice_notes_are_accepted():
    audio = _decode_audio(_opus_in_ogg(), AudioLimits())
    assert 15000 <= len(audio) <= 17000  # ~1 s resampled to 16 kHz mono


@pytest.mark.parametrize("spoken,mg_dl,digit_confidence", [
    ("Meu teste de glicemia deu meia sete", 67, 0.9),    # what the ASR writes with a vocabulary hint
    ("Meu teste de glicemia deu 6 a 7.", 67, 0.8),       # ...and without it
    ("Meu teste de glicemia deu 0.67.", 67, 0.30),       # ...or this one, whose token is low-confidence
    ("manda um ó fiz o teste de 82", 82, 0.63),           # 8 words: "teste" is the glucose context
    ("Fiz o teste de 190.", 190, 0.53),                  # just under the old 0.55 floor
])
def test_real_recordings_that_used_to_fail_now_become_readings(spoken, mg_dl, digit_confidence):
    class Real:
        limits = AudioLimits()

        async def transcribe_async(self, data, language=None):
            return Transcription(spoken, "pt", 4, "fake-test-only", 0.5, digit_confidence)

    body = wav_bytes()
    signed = sign_request(b"w" * 32, "POST", "/internal/extract/audio", str(int(time.time())), "S" * 24, body)
    headers = {
        "content-type": "application/octet-stream", "x-correlation-id": "syntheticCorrelation123",
        "x-worker-timestamp": signed.timestamp, "x-worker-nonce": signed.nonce,
        "x-worker-content-sha256": signed.body_sha256, "x-worker-signature": signed.signature,
    }
    client = TestClient(create_media_app(b"w" * 32, ReplayStore(), transcriber=Real()))
    assessment = client.post("/internal/extract/audio", content=body, headers=headers).json()["assessment"]
    assert assessment["needs_clarification"] is False, assessment
    assert assessment["candidate_value_mg_dl"] == mg_dl


def test_a_low_confidence_reading_is_flagged_and_the_gateway_carries_the_warning():
    from app.api.glico_routes import _trusted_worker_assessment

    flagged = {"status": "review_required", "needs_clarification": False, "clarification_reasons": [],
               "candidate_value_mg_dl": 84, "candidate_confidence": 0.34, "confidence_threshold": 0.25,
               "low_confidence": True}
    assert _trusted_worker_assessment({"assessment": flagged}, "audio") == 84.0
    # the flag never relaxes photos, and an unflagged weak audio reading is still refused
    assert _trusted_worker_assessment({"assessment": flagged}, "image") is None
    assert _trusted_worker_assessment({"assessment": {**flagged, "low_confidence": False,
                                                       "confidence_threshold": 0.5}}, "audio") is None
