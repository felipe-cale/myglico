import json

import httpx
import pytest

from app.services import glico_llm


class _Response:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


def _gemini(intent: dict) -> _Response:
    return _Response(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(intent)}]}}]})


def _fake_client(response, sent):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            sent.update(url=url, payload=json, headers=headers)
            if isinstance(response, Exception):
                raise response
            return response

    return Client


def _call(monkeypatch, response, text="minha glicose deu 132", history=None):
    sent: dict = {}
    monkeypatch.setattr(glico_llm.httpx, "Client", _fake_client(response, sent))
    result = glico_llm.interpret(api_key="k", model="m", timeout=5, text=text, history=history or [],
                                 locale="pt-BR", role="patient", now_iso="2026-10-14 09:00", timezone="America/Sao_Paulo")
    return result, sent


def test_valid_reading_intent_is_parsed_and_only_typed_text_is_sent(monkeypatch):
    result, sent = _call(monkeypatch, _gemini(
        {"intent": "record_reading", "glucose_value": 132, "unit": "mg/dL", "measured_date": "2026-10-14",
         "measured_time": "08:00", "reply": "ok"}))
    assert result["intent"] == "record_reading" and result["glucose_value"] == 132.0
    assert result["measured_date"] == "2026-10-14" and result["measured_time"] == "08:00"
    assert sent["headers"]["x-goog-api-key"] == "k"
    assert [c["parts"][0]["text"] for c in sent["payload"]["contents"]] == ["minha glicose deu 132"]
    assert "responseSchema" in sent["payload"]["generationConfig"]


def test_history_is_trimmed_and_starts_with_a_user_turn(monkeypatch):
    history = [{"role": "assistant", "text": "oi"}] + [{"role": "user", "text": f"m{i}"} for i in range(8)]
    _, sent = _call(monkeypatch, _gemini({"intent": "answer", "reply": "oi"}), history=history)
    contents = sent["payload"]["contents"]
    assert contents[0]["role"] == "user" and len(contents) <= 7


@pytest.mark.parametrize("response", [
    _Response(503, {}), _Response(200, {"candidates": []}), _Response(200, {}),
    _gemini({"intent": "delete_everything"}), _gemini({"intent": "answer"}),
    _gemini({"intent": "record_reading", "unit": "mg/dL"}),
    _gemini({"intent": "record_reading", "glucose_value": 120, "unit": "kg"}),
    httpx.ReadTimeout("slow"),
])
def test_any_failure_or_untrusted_output_returns_none(monkeypatch, response):
    result, _ = _call(monkeypatch, response)
    assert result is None


def test_vague_time_is_dropped_and_reply_is_sanitized(monkeypatch):
    result, _ = _call(monkeypatch, _gemini(
        {"intent": "answer", "reply": "Olá\x00 \x07tudo bem?", "measured_date": "2026-10-14"}))
    assert result["reply"] == "Olá tudo bem?"


@pytest.mark.parametrize("text,expected", [
    ("tenho que tomar quantas unidades de insulina com 250?", True),
    ("how many units of insulin should I take?", True),
    ("¿cuántas unidades de insulina me pongo?", True),
    ("minha glicose deu 128 antes da insulina", False),
    ("quero ver minhas leituras", False),
])
def test_dose_questions_are_caught_without_the_model(text, expected):
    assert glico_llm.is_dose_question(text) is expected
