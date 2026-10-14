"""From an ASR transcript to a glucose reading, as data plus a small decision table.

No I/O and no model here: given the text the speaker said (already normalized by ``spoken``) this decides
whether it holds exactly one glucose value, which unit that value is in, and how sure we are. Adding a case
means adding a row to ``UNIT_RULES`` or a pattern to ``NOT_A_READING``, and a case to the tests.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Callable

from app.media_worker.spoken import normalize_spoken

# A plausible spoken reading below the normal floor is proposed anyway, flagged, instead of refused:
# the speaker's words are shown and the card still needs a confirmation.
LOW_CONFIDENCE_FLOOR = 0.25
MMOL_TO_MG = 18.0182

EXPLICIT_MMOL = re.compile(r"\bmmol\s*/?\s*l\b", re.I)
EXPLICIT_MG = re.compile(r"\b(?:mg\s*/?\s*d[l1]|miligramos?\s+por\s+decilitro)\b", re.I)
# Without a spoken unit the number is only read as a glucose when the speech is about a measurement.
GLUCOSE_CONTEXT = re.compile(
    r"gli[cs]|gluc|a[cç]úcar|azúcar|sugar|diabet|medi[çc]|medic[ií]|medid|measur|resultado|result"
    r"|marcou|deu |mostrou|show|reading|lectura|leitura|lectur|teste|prueba|exame|examen|\btest\b", re.I)
# Times, dates and durations must never become a reading just because the phrase is short.
NOT_A_READING = re.compile(
    r"hora|minut|segund|\bdias?\b|semana|m[eê]s|\bano|vez(?:es)?\b|consulta|reuni|\bs\b|\bàs\b|\bas\b\s+\d"
    r"|hour|minute|second|\bdays?\b|week|month|year|times?\b|o'clock|\d\s*[:/h]\s*\d|\d\s*h\b", re.I)
NUMBER = re.compile(r"(?<![\d.,])(\d{1,4}(?:[.,]\d{1,2})?)(?!\d)")


@dataclass(frozen=True)
class Number:
    raw: str
    value: float
    decimal: bool


@dataclass(frozen=True)
class Reading:
    original_value: float
    unit: str            # "mg/dL" | "mmol/L"
    inferred: bool       # the speaker did not say the unit
    mg_dl: float


@dataclass(frozen=True)
class UnitRule:
    """One way a transcript can tell us the unit. Rules are tried in order; the first that applies wins."""
    name: str
    applies: Callable[[str, Number], bool]
    unit: Callable[[Number], str]
    inferred: bool


def _by_magnitude(number: Number) -> str:
    # Decimals and values under 20 read as mmol/L, everything else as mg/dL (the Brazilian default).
    return "mmol/L" if (number.decimal or number.value < 20) else "mg/dL"


def _plausible(number: Number) -> bool:
    return (number.decimal and 2.0 <= number.value <= 33.3) or (not number.decimal and 20 <= number.value <= 600)


UNIT_RULES: tuple[UnitRule, ...] = (
    UnitRule("explicit_mmol", lambda text, n: bool(EXPLICIT_MMOL.search(text)), lambda n: "mmol/L", False),
    UnitRule("explicit_mg", lambda text, n: bool(EXPLICIT_MG.search(text)), lambda n: "mg/dL", False),
    UnitRule("glucose_context", lambda text, n: bool(GLUCOSE_CONTEXT.search(text)), _by_magnitude, True),
    # "Fiz o teste de 53", "53": a short phrase with one plausible number, in a glucose chat.
    UnitRule("short_plausible",
             lambda text, n: len(text.split()) <= 6 and not NOT_A_READING.search(text) and _plausible(n),
             lambda n: "mmol/L" if n.decimal else "mg/dL", True),
)


def find_number(text: str) -> Number | None:
    """The one number in the text, or None when there are none or several."""
    found = list(dict.fromkeys(NUMBER.findall(text)))
    if len(found) != 1:
        return None
    raw = found[0]
    return Number(raw, float(raw.replace(",", ".")), "." in raw or "," in raw)


def read_transcript(text: str) -> Reading | None:
    """Single number in the transcript -> value in mg/dL with the unit explicit or inferred."""
    number = find_number(text)
    if number is None:
        return None
    rule = next((r for r in UNIT_RULES if r.applies(text, number)), None)
    if rule is None:
        return None
    unit = rule.unit(number)
    mg_dl = round(number.value * MMOL_TO_MG, 1) if unit == "mmol/L" else number.value
    return Reading(number.value, unit, rule.inferred, mg_dl)


def assessment(candidates: list[int], unit_present: bool, confidence: float | None, limits) -> dict:
    """The verdict handed to the gateway: one clear value, or the reasons it needs clarification."""
    reasons = []
    unique = list(dict.fromkeys(candidates))
    if not unit_present:
        reasons.append("unit_missing")
    if len(unique) != 1:
        reasons.append("multiple_candidates" if unique else "value_not_detected")
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


def digit_candidates(text: str) -> list[int]:
    """Explicit 2-4 digit tokens: what the strict path accepts when no reading could be inferred."""
    return [int(raw) for raw in re.findall(r"(?<!\d)\d{2,4}(?!\d)", text)]


def assess_transcript(text: str, language: str | None, confidence: float | None,
                      digit_confidence: float | None, limits) -> tuple[str, dict]:
    """Normalize the transcript and assess it. Returns (spoken_text, assessment).

    The number's own probability decides when the number came out as digits: garbled words around it
    ("Fisidate e Deus 75") must not veto a number the model is sure of. A plausible reading whose number is
    unsure but not negligible is proposed flagged ``low_confidence`` rather than refused.
    """
    spoken = normalize_spoken(text, language)
    if digit_confidence is not None:
        confidence = digit_confidence
    reading = read_transcript(spoken)
    if reading is None:
        return spoken, assessment(digit_candidates(spoken), bool(EXPLICIT_MG.search(spoken)), confidence, limits)
    verdict = assessment([reading.mg_dl], True, confidence, limits)
    if (verdict["needs_clarification"] and verdict["clarification_reasons"] == ["confidence_below_threshold"]
            and confidence is not None and confidence >= LOW_CONFIDENCE_FLOOR):
        verdict = assessment([reading.mg_dl], True, confidence, replace(limits, min_confidence=0.0))
        verdict["low_confidence"] = True
        verdict["confidence_threshold"] = LOW_CONFIDENCE_FLOOR
    verdict.update(candidate_original_value=reading.original_value, candidate_unit=reading.unit,
                   unit_inferred=reading.inferred)
    return spoken, verdict
