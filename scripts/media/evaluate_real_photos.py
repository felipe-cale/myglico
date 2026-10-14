"""Replay real glucometer photos through the worker's photo pipeline.

Folder layout (kept out of git, photos are personal):
  <dir>/manifest.json -> [{"file": "x.jpg", "expected_mg_dl": 167, "meter": "...", "note": "..."}, ...]

Run with the isolated media venv:
  .venv-media\\Scripts\\python.exe scripts/media/evaluate_real_photos.py --dir tmp/real-photos
Photos captured with GLICO_DEV_SAVE_IMAGE_DIR work too once their value is added to a manifest.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "LOCAL")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


async def run(args) -> int:
    from app.media_worker.image import PaddleReadingExtractor
    from app.media_worker.photo import read_photo

    models = Path(args.models)
    engine = PaddleReadingExtractor(str(models / "paddle-det"), str(models / "paddle-rec"))
    await engine.start_async()
    folder = Path(args.dir)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    passed = 0
    for item in manifest:
        body = (folder / item["file"]).read_bytes()
        started = time.monotonic()
        result, assessment, tried = await read_photo(engine, body)
        seconds = time.monotonic() - started
        value = assessment["candidate_value_mg_dl"]
        ok = value == item.get("expected_mg_dl")
        passed += ok
        texts = [(c.text, round(c.confidence or 0, 2)) for c in result.candidates if any(ch.isdigit() for ch in c.text)]
        print(f"{'OK  ' if ok else 'FAIL'} {item['file']:26} {seconds:5.1f}s passes={len(tried)} "
              f"valor={value} esperado={item.get('expected_mg_dl')} {assessment['clarification_reasons']} {texts}")
    await engine.aclose()
    print(f"\n{passed}/{len(manifest)} corretos")
    return 0 if passed == len(manifest) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="tmp/real-photos")
    parser.add_argument("--models", default="tmp/media-f1/models-en")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
