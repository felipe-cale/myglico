"""Create a synthetic Spanish ASR evaluation corpus using a local Piper voice."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import wave

import numpy as np
from piper import PiperVoice


CASES = [
    ("01_value_128.wav", "Mi glucosa está en ciento veintiocho miligramos por decilitro.", 128, "mg/dL", False, "single_value_unit", "review"),
    ("02_value_95.wav", "La lectura fue de noventa y cinco miligramos por decilitro.", 95, "mg/dL", False, "single_value_unit", "review"),
    ("03_value_250.wav", "El resultado del medidor es doscientos cincuenta miligramos por decilitro.", 250, "mg/dL", False, "single_value_unit", "review"),
    ("04_today_time_128.wav", "Hoy a las ocho y media, mi glucosa fue ciento veintiocho miligramos por decilitro.", 128, "mg/dL", False, "today_and_time", "review"),
    ("05_last_night_95.wav", "Ayer por la noche, mi lectura fue noventa y cinco miligramos por decilitro.", 95, "mg/dL", False, "relative_date_and_time", "review"),
    ("06_ambiguous_128.wav", "Ciento veintiocho.", 128, None, True, "value_without_unit", "clarify"),
    ("07_multiple_values.wav", "Mi glucosa fue ciento veintiocho y luego doscientos cincuenta miligramos por decilitro.", None, "mg/dL", True, "multiple_values", "clarify"),
    ("08_ambiguous_95.wav", "Noventa y cinco, sin unidad visible.", 95, None, True, "value_without_unit", "clarify"),
    ("09_silence.wav", None, None, None, False, "silence", "no_speech"),
    ("10_unrelated_speech.wav", "Hola, buenos días. La reunión empieza a las ocho y media.", None, None, False, "unrelated_speech", "reject"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    voice = PiperVoice.load(args.model.resolve(), config_path=args.config.resolve(), use_cuda=False)
    manifest = []
    sample_rate = voice.config.sample_rate
    for filename, utterance, expected_value, expected_unit, needs_clarification, scenario, expected_action in CASES:
        target = args.output / filename
        if utterance is None:
            samples = np.zeros(sample_rate, dtype=np.int16)
            with wave.open(str(target), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes(samples.tobytes())
        else:
            with wave.open(str(target), "wb") as wav:
                voice.synthesize_wav(utterance, wav)
        manifest.append({
            "path": filename,
            "language": "es",
            "expected_value": expected_value,
            "expected_values": [128, 250] if scenario == "multiple_values" else ([expected_value] if expected_value is not None else []),
            "expected_unit": expected_unit,
            "needs_clarification": needs_clarification,
            "expected_action": expected_action,
            "scenario": scenario,
            "synthetic": True,
        })
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"voice": str(args.model.resolve()), "sample_rate": sample_rate, "cases": len(manifest)}, indent=2))


if __name__ == "__main__":
    main()
