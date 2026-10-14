"""Local development launcher for the media worker (single process, no Redis).

Run with the isolated media venv:
  .venv-media\Scripts\python.exe scripts/media/run_local_worker.py --models tmp/media-f1/models-en --secret <>=32 chars>
The nonce store is in memory, so this is for one local worker only.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import threading

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.media_worker.audio import FasterWhisperTranscriber
from app.media_worker.image import PaddleReadingExtractor
from app.media_worker.service import create_media_app


class LocalReplayStore:
    def __init__(self):
        self.values: set[str] = set()
        self.lock = threading.Lock()

    def consume_once(self, nonce: str, expires_at: int) -> bool:  # noqa: ARG002
        with self.lock:
            if nonce in self.values:
                return False
            self.values.add(nonce)
            return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", required=True)
    parser.add_argument("--secret", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8400)
    args = parser.parse_args()
    secret = args.secret.encode()
    if len(secret) < 32:
        raise SystemExit("secret must have at least 32 characters")
    models = Path(args.models)
    app = create_media_app(
        secret,
        LocalReplayStore(),
        PaddleReadingExtractor(str(models / "paddle-det"), str(models / "paddle-rec")),
        transcriber=FasterWhisperTranscriber(str(models / "whisper")),
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
