"""Replay real recordings against the local ASR and the worker's reading rules.

Folder layout (kept out of git, recordings are people's voices):
  <dir>/manifest.json  -> [{"file": "x.ogg", "language": "pt", "said": "...", "expected_mg_dl": 75}, ...]
  <dir>/x.ogg

Run with the isolated media venv:
  .venv-media\Scripts\python.exe scripts/media/evaluate_real_audio.py --dir tmp/real-audio
Use --whisper-dir to compare models. Recordings captured with GLICO_DEV_SAVE_AUDIO_DIR work too once
their .json is turned into a manifest entry.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from app.media_worker.reading import assess_transcript  # noqa: E402
from app.media_worker.audio import AudioLimits  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="tmp/real-audio")
    parser.add_argument("--whisper-dir", default="tmp/media-f1/models-en/whisper")
    parser.add_argument("--no-hint", action="store_true", help="auto-detect the language instead of using the manifest's")
    args = parser.parse_args()

    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio

    folder = Path(args.dir)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    model = WhisperModel(args.whisper_dir, device="cpu", compute_type="int8", local_files_only=True)
    limits = AudioLimits()
    passed = 0
    for item in manifest:
        audio = decode_audio(str(folder / item["file"]), sampling_rate=16000)
        started = time.time()
        segments, info = model.transcribe(audio, beam_size=1, vad_filter=True, word_timestamps=True,
                                          language=None if args.no_hint else item.get("language"))
        segments = list(segments)
        seconds = time.time() - started
        raw = " ".join(s.text.strip() for s in segments)
        digit = [w.probability for s in segments for w in (s.words or []) if any(c.isdigit() for c in w.word)]
        overall = sum(math.exp(s.avg_logprob) for s in segments) / max(1, len(segments))
        # The same function the worker runs in production: normalization, unit, confidence policy.
        _, verdict = assess_transcript(raw, str(info.language), overall, min(digit) if digit else None, limits)
        value = verdict["candidate_value_mg_dl"]
        expected = item.get("expected_mg_dl")
        ok = value is not None if expected is None else value == expected
        passed += ok
        print(f"{'OK  ' if ok else 'FAIL'} {item['file']:22} {seconds:4.1f}s "
              f"valor={value}{' (baixa confiança)' if verdict.get('low_confidence') else ''} esperado={expected} :: {raw!r}")
    print(f"\n{passed}/{len(manifest)} corretos (sem valor esperado: conta se virou leitura)")
    return 0 if passed == len(manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
