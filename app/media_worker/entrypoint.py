"""Private worker launcher; deployment must place this listener on a private network."""

from __future__ import annotations

import os

from app.media_worker.auth import ReplayStore
from app.media_worker.audio import FasterWhisperTranscriber
from app.media_worker.image import PaddleReadingExtractor
from app.media_worker.service import create_media_app


class RedisReplayStore(ReplayStore):
    def __init__(self, url: str):
        from redis import Redis

        if not url:
            raise RuntimeError("shared media worker replay store is not configured")
        self.client = Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)

    def consume_once(self, nonce: str, expires_at: int) -> bool:
        import time

        ttl = max(1, expires_at - int(time.time()))
        return bool(self.client.set(f"myglico:media:nonce:{nonce}", "1", nx=True, ex=ttl))


def _secret() -> bytes:
    # Same key material as the gateway signer: the configured string as UTF-8.
    secret = os.environ.get("MYGLICO_MEDIA_HMAC_SECRET", "").encode()
    if len(secret) < 32:
        raise RuntimeError("media worker HMAC secret is not configured")
    return secret


app = create_media_app(
    _secret(),
    RedisReplayStore(os.environ.get("MYGLICO_MEDIA_REPLAY_REDIS_URL", "")),
    PaddleReadingExtractor(
        os.environ.get("PADDLE_DETECTION_MODEL_DIR"),
        os.environ.get("PADDLE_RECOGNITION_MODEL_DIR"),
    ),
    transcriber=FasterWhisperTranscriber(os.environ.get("FASTER_WHISPER_MODEL_DIR")),
)
