"""Small per-process fixed-window request limiter for abuse-sensitive endpoints."""

from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
from threading import Lock
from time import monotonic


_WINDOW_SECONDS = 60.0
_RULES = {"login": 10, "doctor_search": 30, "doctor_link_request": 10}
_attempts: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def consume(scope: str, ip_address: str, identity: str) -> tuple[bool, int]:
    """Consume one attempt; return (allowed, retry_after_seconds)."""
    limit = _RULES[scope]
    tokens = (
        sha256(f"{scope}\0ip\0{ip_address}".encode("utf-8")).hexdigest(),
        sha256(f"{scope}\0identity\0{identity}".encode("utf-8")).hexdigest(),
    )
    now = monotonic()
    with _lock:
        active = []
        for token in tokens:
            attempts = _attempts[token]
            while attempts and now - attempts[0] >= _WINDOW_SECONDS:
                attempts.popleft()
            active.append((token, attempts))
        blocked = [attempts for _, attempts in active if len(attempts) >= limit]
        if blocked:
            oldest = min(attempts[0] for attempts in blocked)
            return False, max(1, int(_WINDOW_SECONDS - (now - oldest)))
        for _, attempts in active:
            attempts.append(now)
        if len(_attempts) > 10000:
            expired = [key for key, values in _attempts.items() if not values or now - values[-1] >= _WINDOW_SECONDS]
            for key in expired:
                _attempts.pop(key, None)
        return True, 0


def reset_for_tests() -> None:
    with _lock:
        _attempts.clear()
