"""Spoken numbers and units in an ASR transcript, normalized to digits (pt, en, es).

Two layers, on purpose:

* **Generic**: number words ("cento e vinte e oito", "ninety eight", "ciento veinte") are converted by
  ``text2num``, a maintained library, instead of hand-kept dictionaries for three languages.
* **Domain**: what a glucose log needs on top, as small declarative tables (``RUN_WORDS``, ``REPAIRS``,
  ``UNITS``): dictated digit runs ("um dois zero", "meia quatro"), the broken forms Whisper writes for
  them ("6 a 7", "0.67"), and the unit phrases ("miligramas por decilitro").

Anything that does not parse cleanly is left as the speaker said it, so the strict digit-and-unit gate
downstream stays the only thing that can create a reading. To handle a new case add a row to a table and a
case to ``tests/unit/media_worker/test_spoken.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable
import unicodedata

from text_to_num import alpha2digit

LANGUAGES = ("pt", "en", "es")


@dataclass(frozen=True)
class Repair:
    """A rewrite applied to the text: ``pattern`` -> ``replace``. ``why`` documents the speech it handles."""
    name: str
    pattern: re.Pattern
    replace: Callable[[re.Match], str]
    why: str


# Words that count as a single digit when they sit next to another digit while dictating one by one.
# Alone they keep their normal meaning: "uma glicose", "oito e meia" (half past eight), "meia hora".
RUN_WORDS: dict[str, dict[str, int]] = {
    "pt": {"zero": 0, "um": 1, "uma": 1, "meia": 6},   # Brazilians say "meia" for 6: "meia quatro" = 64
    "en": {"zero": 0, "oh": 0, "one": 1},
    "es": {"cero": 0, "un": 1, "uno": 1, "una": 1},
}

_NOT_AFTER_DIGIT = r"(?<![\d.,])"
_NOT_BEFORE_DIGIT = r"(?!\d|[.,]\d)"

# Whisper sometimes mixes digits and connectors, breaks a dictated pair apart, or reads it as a decimal.
REPAIRS: tuple[Repair, ...] = (
    Repair("digit_a_digit", re.compile(_NOT_AFTER_DIGIT + r"(\d)\s+a\s+(\d)" + _NOT_BEFORE_DIGIT),
           lambda m: m.group(1) + m.group(2), 'Whisper writes a dictated "meia sete" as "6 a 7"'),
    Repair("zero_point_pair", re.compile(_NOT_AFTER_DIGIT + r"0[.,](\d{2,3})(?!\d)"),
           lambda m: m.group(1), 'Whisper writes a dictated "meia sete" as "0.67"'),
    Repair("tens_and_unit", re.compile(_NOT_AFTER_DIGIT + r"([2-9]0)\s+(?:y|e|and)\s+([1-9])" + _NOT_BEFORE_DIGIT),
           lambda m: str(int(m.group(1)) + int(m.group(2))), '"90 y 5" for "noventa y cinco"'),
    Repair("hundreds_and_rest", re.compile(_NOT_AFTER_DIGIT + r"([1-9]00)\s+(?:y|e|and)\s+([1-9]\d?)" + _NOT_BEFORE_DIGIT),
           lambda m: str(int(m.group(1)) + int(m.group(2))), '"100 e 20" for "cento e vinte"'),
)

# Unit phrases: "miligramas por decilitro", "mg per deciliter" (also as the ASR misspells them) -> mg/dL.
UNITS: tuple[Repair, ...] = (
    Repair("mg_dl", re.compile(r"\b(?:miligramas?|milligrams?|miligramos?|mg)\s*(?:por|per|/)\s*(?:deci\w*|dl)\b", re.I),
           lambda m: "mg/dL", "milligrams per deciliter"),
    Repair("mmol_l", re.compile(r"\b(?:milimol(?:es)?|millimol(?:es)?|mmol)\s*(?:por|per|/)\s*(?:litros?|liters?|litres?|l)\b", re.I),
           lambda m: "mmol/L", "millimoles per liter"),
)


def _fold(word: str) -> str:
    word = unicodedata.normalize("NFKD", word.strip(".,;:!?¿¡").lower())
    return "".join(ch for ch in word if not unicodedata.combining(ch))


def _digit_of(token: str, lang: str) -> int | None:
    word = _fold(token)
    if word.isdigit() and len(word) == 1:
        return int(word)
    return RUN_WORDS[lang].get(word)


def _join_digit_runs(text: str, lang: str) -> str:
    """Two or more dictated digits in a row become one number: "um 2 0" -> "120", "meia quatro" -> "64"."""
    words = text.split()
    out: list[str] = []
    i = 0
    while i < len(words):
        j, digits = i, []
        while j < len(words) and (value := _digit_of(words[j], lang)) is not None:
            digits.append(str(value))
            j += 1
        if len(digits) >= 2:
            tail = re.search(r"[.,;:!?]+$", words[j - 1])
            out.append("".join(digits) + (tail.group(0) if tail else ""))
            i = j
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


def _apply(text: str, rules: tuple[Repair, ...]) -> str:
    for rule in rules:
        text = rule.pattern.sub(rule.replace, text)
    return text


def _normalize_as(text: str, lang: str) -> str:
    text = alpha2digit(text, lang)
    text = _join_digit_runs(text, lang)
    return _apply(_apply(text, REPAIRS), UNITS)


def normalize_spoken(text: str, language: str | None = None) -> str:
    """The transcript with spoken numbers and units rewritten as digits and mg/dL, mmol/L.

    With an unknown language each of pt, en and es is tried and the rewrite that produced the most
    digits wins (the words of different languages do not collide in practice).
    """
    if not text.split():
        return text
    lang = (language or "")[:2]
    candidates = [lang] if lang in LANGUAGES else list(LANGUAGES)
    results = [_normalize_as(text, code) for code in candidates]
    return max(results, key=lambda result: sum(ch.isdigit() for ch in result))
