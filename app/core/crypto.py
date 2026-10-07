"""Authenticated field encryption, blind indexes, and password hashing.

Encryption keys and the independent blind-index key are 32-byte hexadecimal
values supplied through MYGLICO_* environment variables. Field payloads carry
their key version and a fresh 12-byte AES-GCM nonce; AAD binds each value to
its table, column, and row ID.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import string

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app.core.config import get_settings


_PAYLOAD_PREFIX = b"MG"
_NONCE_BYTES = 12
_SHORTID_ALPHABET = string.ascii_uppercase + string.digits
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_LENGTH = 32


def _key_from_hex(value: str | None, setting_name: str) -> bytes:
    if not value:
        raise RuntimeError(f"{setting_name} must be configured before using protected data")
    try:
        key = bytes.fromhex(value)
    except ValueError as exc:
        raise RuntimeError(f"{setting_name} must contain 64 hexadecimal characters") from exc
    if len(key) != 32:
        raise RuntimeError(f"{setting_name} must contain 64 hexadecimal characters")
    return key


def _encryption_key(version: int) -> bytes:
    settings = get_settings()
    key_value = {1: settings.encryption_key_v1, 2: settings.encryption_key_v2}.get(version)
    if key_value is None:
        raise RuntimeError(f"Encryption key version {version} is not configured")
    return _key_from_hex(key_value, f"MYGLICO_ENCRYPTION_KEY_V{version}")


def encrypt_field(value: str | None, *, table: str, column: str, record_id: str) -> bytes | None:
    """Encrypt one UTF-8 field and return a versioned binary payload."""
    if value is None:
        return None
    settings = get_settings()
    version = settings.active_encryption_key_version
    if not 1 <= version <= 255:
        raise RuntimeError("MYGLICO_ACTIVE_ENCRYPTION_KEY_VERSION must be between 1 and 255")
    nonce = secrets.token_bytes(_NONCE_BYTES)
    aad = f"{table}:{column}:{record_id}".encode("utf-8")
    ciphertext = AESGCM(_encryption_key(version)).encrypt(nonce, value.encode("utf-8"), aad)
    return _PAYLOAD_PREFIX + bytes([version]) + nonce + ciphertext


def decrypt_field(payload: bytes | bytearray | memoryview | None, *, table: str, column: str, record_id: str) -> str | None:
    """Decrypt a field, rejecting tampering or ciphertext moved to another field."""
    if payload is None:
        return None
    raw = bytes(payload)
    minimum = len(_PAYLOAD_PREFIX) + 1 + _NONCE_BYTES + 16
    if len(raw) < minimum or not raw.startswith(_PAYLOAD_PREFIX):
        raise ValueError("Invalid encrypted field payload")
    version = raw[len(_PAYLOAD_PREFIX)]
    nonce_start = len(_PAYLOAD_PREFIX) + 1
    nonce = raw[nonce_start : nonce_start + _NONCE_BYTES]
    ciphertext = raw[nonce_start + _NONCE_BYTES :]
    aad = f"{table}:{column}:{record_id}".encode("utf-8")
    plaintext = AESGCM(_encryption_key(version)).decrypt(nonce, ciphertext, aad)
    return plaintext.decode("utf-8")


def normalize_email(email: str) -> str:
    """Canonical login email: trim surrounding whitespace and lowercase."""
    return email.strip().lower()


def normalize_crm_uf(crm: str, uf: str) -> tuple[str, str]:
    """Normalize CRM and UF by trimming outer whitespace and uppercasing.

    CRM punctuation and internal characters are preserved to avoid collapsing
    distinct registration formats. UF is an uppercase two-letter state code.
    """
    return crm.strip().upper(), uf.strip().upper()


def _lookup_hmac(purpose: str, canonical_value: str) -> str:
    key = _key_from_hex(get_settings().lookup_hmac_key, "MYGLICO_LOOKUP_HMAC_KEY")
    message = f"myglico:{purpose}:v1:{canonical_value}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def email_lookup(email: str) -> str:
    return _lookup_hmac("email", normalize_email(email))


def crm_uf_lookup(crm: str, uf: str) -> str:
    canonical_crm, canonical_uf = normalize_crm_uf(crm, uf)
    # JSON array serialization is unambiguous even when CRM contains separators.
    canonical = json.dumps([canonical_crm, canonical_uf], ensure_ascii=False, separators=(",", ":"))
    return _lookup_hmac("crm_uf", canonical)


def hash_password(password: str) -> str:
    """Hash with scrypt and a fresh salt per password; output is self-describing."""
    salt = secrets.token_bytes(16)
    digest = Scrypt(salt=salt, length=_SCRYPT_LENGTH, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P).derive(
        password.encode("utf-8")
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = password_hash.split("$")
        if algorithm != "scrypt":
            return False
        Scrypt(
            salt=bytes.fromhex(salt_hex),
            length=len(bytes.fromhex(digest_hex)),
            n=int(n),
            r=int(r),
            p=int(p),
        ).verify(
            password.encode("utf-8"), bytes.fromhex(digest_hex)
        )
        return True
    except (InvalidKey, ValueError, TypeError):
        return False


def generate_short_id(is_taken=None, *, attempts: int = 32) -> str:
    """Generate a six-character CSPRNG code, retrying while the caller says it exists."""
    for _ in range(attempts):
        candidate = "".join(secrets.choice(_SHORTID_ALPHABET) for _ in range(6))
        if is_taken is None or not is_taken(candidate):
            return candidate
    raise RuntimeError("Unable to allocate a unique SHORTID after repeated collisions")
