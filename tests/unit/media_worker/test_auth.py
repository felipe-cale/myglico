from app.media_worker.auth import sign_request, verify_request


class MemoryReplayStore:
    def __init__(self):
        self.nonces = set()

    def consume_once(self, nonce, expires_at):
        if nonce in self.nonces:
            return False
        self.nonces.add(nonce)
        return True


def test_worker_signature_binds_body_path_and_nonce():
    secret = b"s" * 32
    body = b"synthetic media bytes"
    replay = MemoryReplayStore()
    signed = sign_request(secret, "POST", "/internal/extract/image", "1000", "A" * 24, body)

    assert verify_request(secret, "POST", "/internal/extract/image", body, signed, replay, now=1000)
    assert not verify_request(secret, "POST", "/internal/extract/image", body, signed, replay, now=1000)


def test_worker_signature_rejects_tampering_expiry_and_unavailable_replay_store():
    secret = b"s" * 32
    body = b"safe"
    signed = sign_request(secret, "POST", "/extract", "1000", "B" * 24, body)
    replay = MemoryReplayStore()

    assert not verify_request(secret, "POST", "/different", body, signed, replay, now=1000)
    assert not verify_request(secret, "POST", "/extract", b"changed", signed, replay, now=1000)
    assert not verify_request(secret, "POST", "/extract", body, signed, replay, now=1031)
    headers = type("H", (), {
        "timestamp": signed.timestamp, "nonce": signed.nonce, "body_sha256": signed.body_sha256,
        "signature": signed.signature,
    })()
    unavailable = type("Store", (), {"consume_once": lambda *_: (_ for _ in ()).throw(RuntimeError())})()
    assert not verify_request(secret, "POST", "/extract", body, headers, unavailable, now=1000)
