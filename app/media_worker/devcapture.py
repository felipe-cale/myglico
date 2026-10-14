"""Development-only capture of received media (off unless the matching env var is set).

Production never persists media. These helpers keep recordings and photos made while testing locally,
with their diagnosis, so they can be replayed against other models (scripts/media/evaluate_real_*.py).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import time


def save_audio(body: bytes) -> Path | None:
    """Development only: keep received audio for offline evaluation (GLICO_DEV_SAVE_AUDIO_DIR).

    Off by default. Production never persists media; this exists so recordings made while testing
    locally can be replayed against different models.
    """
    folder = os.environ.get("GLICO_DEV_SAVE_AUDIO_DIR")
    if not folder:
        return None
    if body[:4] == b"RIFF":
        suffix = ".wav"
    elif body[:4] == b"OggS":
        suffix = ".ogg"
    elif body[:4] == b"\x1a\x45\xdf\xa3":
        suffix = ".webm"
    elif body[4:8] == b"ftyp":
        suffix = ".m4a"
    else:
        suffix = ".bin"
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{time.strftime('%Y%m%d-%H%M%S')}-{len(list(target.glob('*.json'))) + 1:03d}{suffix}"
    path.write_bytes(body)
    return path


def save_image(body: bytes) -> Path | None:
    """Development only (GLICO_DEV_SAVE_IMAGE_DIR): keep received photos for offline evaluation."""
    folder = os.environ.get("GLICO_DEV_SAVE_IMAGE_DIR")
    if not folder:
        return None
    if body[:3] == b"\xff\xd8\xff":
        suffix = ".jpg"
    elif body[:4] == b"\x89PNG":
        suffix = ".png"
    elif body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        suffix = ".webp"
    else:
        suffix = ".bin"
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{time.strftime('%Y%m%d-%H%M%S')}-{len(list(target.glob('*.json'))) + 1:03d}{suffix}"
    path.write_bytes(body)
    return path


def note(path: Path | None, payload: dict) -> None:
    if path is not None:
        path.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
