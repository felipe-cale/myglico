"""Reading a glucometer photo: first pass, cheaper-first retries, then the agreement rule.

Pure decisions plus one async pipeline (``read_photo``) that drives an OCR engine; no HTTP here.
"""

from __future__ import annotations

import re
import time

from app.media_worker.image import MediaError, enhanced_variants, prepare_for_ocr
from app.media_worker.reading import assessment as build_assessment


RETRY_BUDGET_SECONDS = 10.0

def image_pick(result, limits) -> tuple[list[int], float | None]:
    """Pick the display reading among the digit-only lines of one OCR pass."""
    # Only digit-only display lines qualify as candidate readings; separators
    # are excluded so dates and clock strings are not treated as glucose.
    readings = []
    for item in result.candidates:
        if re.fullmatch(r"\s*\d{2,4}\s*", item.text):
            height = (item.box[3] - item.box[1]) if item.box else 0
            readings.append((int(item.text.strip()), item.confidence, height))
    in_range = [r for r in readings if limits.min_glucose_mg_dl <= r[0] <= limits.max_glucose_mg_dl]
    # Meters print the result in the largest digits; with several plausible
    # numbers (time, date, memory slot) take the clearly tallest one.
    chosen = in_range
    if len(in_range) > 1:
        ranked = sorted(in_range, key=lambda r: r[2], reverse=True)
        if ranked[0][2] > 0 and ranked[0][2] >= 1.25 * ranked[1][2]:
            chosen = [ranked[0]]
    numeric = [r[0] for r in chosen] if chosen else [r[0] for r in readings]
    numeric_confidence = [r[1] for r in (chosen or readings) if r[1] is not None]
    return numeric, (min(numeric_confidence) if numeric_confidence else None)


def image_assessment(result, limits) -> dict:
    """Assess one OCR pass. A missing unit is assumed mg/dL: the proposal is still reviewed and
    editable by the user before anything is written."""
    numeric, confidence = image_pick(result, limits)
    return build_assessment(numeric, True, confidence, limits)


def agreed_assessment(passes, limits) -> tuple[object, dict] | None:
    """Two independent reads of the same photo that give the same in-range value are trusted even
    when each one's confidence is below the single-pass floor (but not below half of it)."""
    floor = max(0.5, limits.min_confidence * 0.8)
    votes: dict[int, list] = {}
    for result in passes:
        numeric, confidence = image_pick(result, limits)
        unique = list(dict.fromkeys(numeric))
        if len(unique) == 1 and confidence is not None and confidence >= floor \
                and limits.min_glucose_mg_dl <= unique[0] <= limits.max_glucose_mg_dl:
            votes.setdefault(unique[0], []).append((result, confidence))
    for value, entries in votes.items():
        if len(entries) >= 2:
            from dataclasses import replace
            best = max(entries, key=lambda entry: entry[1])
            agreed = build_assessment([value], True, min(entry[1] for entry in entries), replace(limits, min_confidence=0.0))
            agreed["confidence_threshold"] = floor
            agreed["agreed_passes"] = len(entries)
            return best[0], agreed
    return None


async def read_photo(engine, body: bytes):
    """Full photo pipeline: first pass at a working size, then cheaper-first retries on other views of
    the same photo, then the agreement rule. Returns (result, assessment, passes)."""
    result = await engine.extract_async(prepare_for_ocr(body))
    assessment = image_assessment(result, engine.limits)
    tried = [result]
    if not assessment["needs_clarification"]:
        return result, assessment, tried
    if any(re.fullmatch(r"\s*(hi|lo)\s*", item.text, re.I) for item in result.candidates):
        return result, assessment, tried  # an out-of-range signal is never retried into a value
    started = time.monotonic()
    for variant in enhanced_variants(body):
        # Extra passes must never push the answer past the gateway's own deadline.
        if time.monotonic() - started > RETRY_BUDGET_SECONDS:
            break
        try:
            retry = await engine.extract_async(variant)
        except MediaError:
            break
        tried.append(retry)
        again = image_assessment(retry, engine.limits)
        if not again["needs_clarification"]:
            return retry, again, tried
    agreed = agreed_assessment(tried, engine.limits) if len(tried) > 1 else None
    if agreed is not None:
        return agreed[0], agreed[1], tried
    return result, assessment, tried
