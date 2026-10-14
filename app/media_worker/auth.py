"""HMAC authentication primitives for the private media worker boundary."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import re
import time
from typing import Protocol


_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{22,100}$")


class ReplayStore(Protocol):
    def consume_once(self, nonce: str, expires_at: int) -> bool: ...


@dataclass(frozen=True)
class WorkerSignature:
    timestamp: str
    nonce: str
    body_sha256: str
    signature: str


def signing_payload(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    """Build the canonical signature payload; identity and cookies are excluded."""
    digest = hashlib.sha256(body).hexdigest()
    return "\n".join((method.upper(), path, timestamp, nonce, digest)).encode("ascii")


def sign_request(secret: bytes, method: str, path: str, timestamp: str, nonce: str, body: bytes) -> WorkerSignature:
    if len(secret) < 32:
        raise ValueError("worker secret must contain at least 32 bytes")
    payload = signing_payload(method, path, timestamp, nonce, body)
    return WorkerSignature(timestamp, nonce, hashlib.sha256(body).hexdigest(), hmac.new(secret, payload, hashlib.sha256).hexdigest())


def verify_request(
    secret: bytes,
    method: str,
    path: str,
    body: bytes,
    headers: WorkerSignature,
    replay_store: ReplayStore,
    *,
    now: int | None = None,
    max_skew_seconds: int = 30,
) -> bool:
    """Verify request signature and atomically consume a short-lived nonce."""
    if len(secret) < 32 or max_skew_seconds < 1:
        return False
    if not _NONCE_RE.fullmatch(headers.nonce):
        return False
    if not headers.timestamp.isascii() or not headers.timestamp.isdecimal():
        return False
    try:
        issued_at = int(headers.timestamp)
    except ValueError:
        return False
    current = int(time.time()) if now is None else now
    if abs(current - issued_at) > max_skew_seconds:
        return False
    actual_digest = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(actual_digest, headers.body_sha256):
        return False
    payload = signing_payload(method, path, headers.timestamp, headers.nonce, body)
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, headers.signature):
        return False
    try:
        return replay_store.consume_once(headers.nonce, issued_at + max_skew_seconds)
    except Exception:
        # A missing/unavailable shared replay store must fail closed.
        return False
