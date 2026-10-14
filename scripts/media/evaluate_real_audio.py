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

from app.media_worker.service import _assessment, _audio_reading  # noqa: E402
from app.media_worker.audio import AudioLimits  # noqa: E402
from app.media_worker.spoken import normalize_spoken  # noqa: E402


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
        spoken = normalize_spoken(raw, str(info.language))
        digit = [w.probability for s in segments for w in (s.words or []) if any(c.isdigit() for c in w.word)]
        overall = sum(math.exp(s.avg_logprob) for s in segments) / max(1, len(segments))
        confidence = min(digit) if digit else overall
        reading = _audio_reading(spoken)
        assessment = _assessment([reading["mg_dl"]], True, confidence, limits) if reading else None
        value = assessment["candidate_value_mg_dl"] if assessment else None
        ok = value == item.get("expected_mg_dl")
        passed += ok
        print(f"{'OK  ' if ok else 'FAIL'} {item['file']:22} {seconds:4.1f}s conf={confidence:.2f} "
              f"valor={value} esperado={item.get('expected_mg_dl')} :: {raw!r}")
    print(f"\n{passed}/{len(manifest)} corretos")
    return 0 if passed == len(manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
