"""Evaluate a local faster-whisper snapshot against synthetic WAV fixtures.

The fixtures must be synthetic/authorized recordings with an adjacent JSON
manifest: [{"path": "pt.wav", "language": "pt", "expected_value": 128}].
No fixture bytes or transcript content are written by this script.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import re
import sys
import time
import hashlib

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.media_worker.audio import FasterWhisperTranscriber
from app.media_worker.service import _assessment, _audio_numeric_candidates


_ES_UNITS = {
    "cero": 0, "uno": 1, "una": 1, "un": 1, "dos": 2, "tres": 3,
    "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
    "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
    "quince": 15, "dieciséis": 16, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21,
    "veintiún": 21, "veintidós": 22, "veintidos": 22, "veintitrés": 23,
    "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "veintiséis": 26,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}
_ES_TENS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
            "setenta": 70, "ochenta": 80, "noventa": 90}
_ES_HUNDREDS = {"cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300,
                "cuatrocientos": 400, "quinientos": 500, "seiscientos": 600,
                "setecientos": 700, "ochocientos": 800, "novecientos": 900}


def _spanish_numbers(text: str) -> list[int]:
    # Clock phrases are not glucose values. Remove the common spoken-time
    # expression before scanning candidate numbers, independent of word order.
    text = re.sub(r"\ba\s+las\b.*?\b(?:media|cuarto|en\s+punto)\b", " ", text, flags=re.I)
    tokens = re.findall(r"[a-záéíóúüñ]+|\d+(?:[.,]\d+)?", text.casefold())
    values: list[int] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if re.fullmatch(r"\d+(?:[.,]\d+)?", token):
            value = float(token.replace(",", "."))
            values.append(int(value) if value.is_integer() else round(value))
            i += 1
            continue
        total = 0
        consumed = 0
        if token in _ES_HUNDREDS:
            total += _ES_HUNDREDS[token]
            consumed = 1
        elif token == "mil":
            total += 1000
            consumed = 1
        j = i + consumed
        if j < len(tokens) and tokens[j] in _ES_TENS:
            total += _ES_TENS[tokens[j]]
            consumed += 1
            j += 1
            if j < len(tokens) and tokens[j] in _ES_UNITS:
                total += _ES_UNITS[tokens[j]]
                consumed += 1
            elif j + 1 < len(tokens) and tokens[j] == "y" and (
                tokens[j + 1] in _ES_UNITS or re.fullmatch(r"\d+", tokens[j + 1])
            ):
                token_value = _ES_UNITS.get(tokens[j + 1])
                total += token_value if token_value is not None else int(tokens[j + 1])
                consumed += 2
        elif j < len(tokens) and tokens[j] in _ES_UNITS:
            total += _ES_UNITS[tokens[j]]
            consumed += 1
        if consumed:
            values.append(total)
            i += consumed
        else:
            i += 1
    return values


def _extract_value(text: str, unit_present: bool) -> tuple[int | None, list[int]]:
    values = _spanish_numbers(text)
    if unit_present:
        # For relative-time utterances, prefer numbers after the last clinical
        # subject/action anchor. Multiple values after that anchor stay ambiguous.
        anchors = [m.end() for m in re.finditer(r"\b(?:glucosa|lectura|lecturas|valor|resultado|medidor)\b", text, re.I)]
        if anchors:
            scoped = _spanish_numbers(text[max(anchors):])
            if scoped:
                values = scoped
    unique = list(dict.fromkeys(values))
    return (unique[0] if len(unique) == 1 else None), unique


async def evaluate(model_dir: str, manifest_path: Path) -> list[dict]:
    cases = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    proc = psutil.Process()
    results = []
    cold_samples, warm_samples = [], []
    for case in cases:
        case_started = time.perf_counter()
        data = (manifest_path.parent / case["path"]).read_bytes()
        engine = FasterWhisperTranscriber(model_dir)
        peak = proc.memory_info().rss
        startup_started = time.perf_counter()
        await engine.start_async()
        cold_startup_ms = round((time.perf_counter() - startup_started) * 1000)

        async def run_one():
            started = time.perf_counter()
            task = asyncio.create_task(engine.transcribe_async(data))
            local_peak = peak
            while not task.done():
                try:
                    local_peak = max(local_peak, proc.memory_info().rss + sum(
                        child.memory_info().rss for child in proc.children(recursive=True)))
                except (psutil.NoSuchProcess, psutil.AccessDenied): pass
                await asyncio.sleep(0.05)
            return await task, round((time.perf_counter() - started) * 1000), local_peak
        try:
            result, cold_inference_ms, peak = await run_one()
            cold_total_ms = cold_startup_ms + cold_inference_ms
            cold_samples.append(cold_total_ms)
            warm_result, warm_ms, warm_peak = await run_one()
            warm_samples.append(warm_ms)
            peak = max(peak, warm_peak)
            unit_present = bool(re.search(
                r"\b(?:mg\s*/?\s*d[l1]|miligramos?\s+por\s+decilitro)\b", result.text, re.I
            ))
            recognized, value_candidates = _extract_value(result.text, unit_present)
            worker_candidates = _audio_numeric_candidates(result.text)
            assessment = _assessment(worker_candidates, unit_present, result.confidence, engine.limits)
            expected_values = case.get("expected_values")
            if expected_values is None:
                expected_values = [case["expected_value"]] if case.get("expected_value") is not None else []
            needs_clarification = bool(case.get("needs_clarification", False))
            review_should_clarify = len(value_candidates) != 1 or not unit_present
            review_action = (
                "reject" if not value_candidates and not unit_present
                else "clarify" if review_should_clarify
                else "review"
            )
            expected_action = case.get("expected_action", "clarify" if needs_clarification else "review")
            results.append({
                "language_expected": case["language"],
                "language_detected": result.language,
                "value_expected": case["expected_value"],
                "value_recognized": recognized,
                "value_candidates": value_candidates,
                "worker_digit_candidates": worker_candidates,
                "value_exact": recognized == case.get("expected_value") if case.get("expected_value") is not None else None,
                "expected_values_all_present": sorted(value_candidates) == sorted(expected_values) if expected_values else not value_candidates,
                "unit_expected": case.get("expected_unit"),
                "unit_recognized": unit_present,
                "unit_exact": unit_present == (case.get("expected_unit") == "mg/dL"),
                "scenario": case.get("scenario"),
                "needs_clarification": needs_clarification,
                "worker_requests_clarification": assessment["needs_clarification"],
                "assessment": assessment,
                "review_should_clarify": review_should_clarify,
                "review_action": review_action,
                "expected_action": expected_action,
                "review_policy_match": review_action == expected_action,
                "transcript_sha256": hashlib.sha256(result.text.encode("utf-8")).hexdigest(),
                "confidence": result.confidence,
                "cold_startup_ms": cold_startup_ms,
                "cold_inference_ms": cold_inference_ms,
                "cold_total_ms": cold_total_ms,
                "warm_inference_ms": warm_ms,
                "elapsed_ms": result.elapsed_ms,
                "wall_ms": cold_inference_ms,
                "peak_rss_mib_observed": round(peak / 1024**2, 1),
            })
        except Exception as exc:
            expected_action = case.get("expected_action", "clarify" if case.get("needs_clarification") else "review")
            review_action = "no_speech" if getattr(exc, "code", "") == "speech_not_detected" else "clarify_or_manual"
            results.append({"language_expected": case["language"], "scenario": case.get("scenario"),
                "error_code": getattr(exc, "code", "evaluation_failed"),
                "elapsed_ms": round((time.perf_counter() - case_started) * 1000),
                "peak_rss_mib_observed": round(peak / 1024**2, 1),
                "worker_requests_clarification": False,
                "review_action": review_action,
                "expected_action": expected_action,
                "review_policy_match": review_action == expected_action})
        del data
        await engine.aclose()
    results.append({"summary": {
        "cold_samples_n": len(cold_samples), "cold_p50_ms": _percentile(cold_samples, .50),
        "cold_p95_ms": _percentile(cold_samples, .95), "warm_samples_n": len(warm_samples),
        "warm_p50_ms": _percentile(warm_samples, .50), "warm_p95_ms": _percentile(warm_samples, .95),
    }})
    return results


def _percentile(values: list[int], quantile: float) -> int | None:
    if not values: return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * quantile))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = asyncio.run(evaluate(args.model_dir, args.manifest))
    encoded = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
