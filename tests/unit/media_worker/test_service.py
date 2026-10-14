import time

from fastapi.testclient import TestClient

from app.media_worker.auth import sign_request
from app.media_worker.image import Extraction, ImageLimits, TextCandidate
from app.media_worker.service import create_media_app


class ReplayStore:
    def __init__(self):
        self.used = set()

    def consume_once(self, nonce, expires_at):
        if nonce in self.used:
            return False
        self.used.add(nonce)
        return True


class FakeExtractor:
    limits = ImageLimits(max_bytes=32)
    calls = 0

    async def extract_async(self, data):
        self.calls += 1
        assert data == b"synthetic"
        return Extraction((TextCandidate("128 mg/dL", 0.99, (1, 2, 3, 4)),), "fake-test-only", 1)


def signed_headers(body, nonce):
    timestamp = str(int(time.time()))
    signed = sign_request(b"w" * 32, "POST", "/internal/extract/image", timestamp, nonce, body)
    return {
        "content-type": "application/octet-stream",
        "x-correlation-id": "syntheticCorrelation123",
        "x-worker-timestamp": signed.timestamp,
        "x-worker-nonce": signed.nonce,
        "x-worker-content-sha256": signed.body_sha256,
        "x-worker-signature": signed.signature,
    }


def test_private_endpoint_authenticates_replay_and_returns_no_store_result():
    engine = FakeExtractor()
    client = TestClient(create_media_app(b"w" * 32, ReplayStore(), engine))
    body = b"synthetic"
    headers = signed_headers(body, "A" * 24)

    response = client.post("/internal/extract/image", content=body, headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["candidates"][0]["text"] == "128 mg/dL"
    assert engine.calls == 1
    assert client.post("/internal/extract/image", content=body, headers=headers).status_code == 401
    assert engine.calls == 1


def test_private_endpoint_rejects_oversized_stream_before_ocr():
    engine = FakeExtractor()
    client = TestClient(create_media_app(b"w" * 32, ReplayStore(), engine))
    response = client.post(
        "/internal/extract/image",
        content=b"x" * 33,
        headers=signed_headers(b"x" * 33, "B" * 24),
    )
    assert response.status_code == 413
    assert engine.calls == 0

