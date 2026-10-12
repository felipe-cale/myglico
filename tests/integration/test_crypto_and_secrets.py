"""Field encryption, AAD, password hashing and secret leakage.

Covers AUT-CA-07, AUT-CA-08, AUT-CA-22, AUT-CA-23 and CSCW-CA-31.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

import pytest

from conftest import World, raw_execute, table_columns

SENSITIVE_VALUES = ("e2e.myglico.invalid", "Paciente A", "9000001")  # e-mail domain, display name, CRM


def _all_cells(table: str) -> list[tuple[str, object]]:
    columns = table_columns(table)
    cells = []
    for row in raw_execute(f"SELECT * FROM {table}"):
        cells.extend(zip(columns, row))
    return cells


def _as_bytes(value: object) -> bytes:
    if value is None:
        return b""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    return str(value).encode("utf-8")


def test_aut_ca_07_direct_table_reads_do_not_reveal_protected_fields(world: World):
    """AUT-CA-07: SELECTs over accounts/patients/doctors reveal no protected value.

    After seeding the five profiles, read every column of user_accounts,
    patients and doctors and assert no plaintext e-mail, name, CRM, UF or
    password material is stored in any column.
    """
    marker = os.urandom(4).hex()
    patient_a = world.patient(display_name=f"Paciente A {marker}")
    patient_b = world.patient(display_name=f"Paciente B {marker}")
    doctor_a = world.doctor(display_name=f"Doutor A {marker}", crm=f"9000001{marker}", uf="RJ")
    doctor_b = world.doctor(display_name=f"Doutor B {marker}", crm=f"9000002{marker}", uf="MG")
    patient_c = world.patient(display_name=f"Paciente C {marker}")
    actors = (patient_a, patient_b, doctor_a, doctor_b, patient_c)

    forbidden: list[bytes] = [marker.encode()]
    for actor in actors:
        forbidden += [actor.email.encode(), actor.email.split("@")[0].encode(),
                      actor.display_name.encode(), actor.password.encode()]
        if actor.crm:
            forbidden.append(actor.crm.encode())
    for table in ("user_accounts", "patients", "doctors", "user_sessions", "provenance_events",
                  "notifications", "patient_doctor_links"):
        blob = b"\x00".join(_as_bytes(value) for _, value in _all_cells(table))
        for secret in forbidden:
            assert secret not in blob, (table, secret[:3])
        if table == "user_accounts":
            assert b"@" + b"integration.myglico.invalid" not in blob
    # UF is two letters, so assert per column instead of substring search.
    for column, value in _all_cells("doctors"):
        assert value not in ("RJ", "MG", b"RJ", b"MG"), column
    # And the encrypted columns really are versioned AES-GCM payloads.
    for column, value in _all_cells("doctors") + _all_cells("user_accounts") + _all_cells("patients"):
        if column.endswith("_encrypted") and value is not None:
            assert isinstance(value, bytes) and value[:2] == b"MG", column


def test_aut_ca_07_free_text_glucose_notes_are_not_stored_in_plaintext(world: World):
    """AUT-CA-07 / CSCW-CA-31: free-text notes typed by the patient are not readable by SELECT.

    Regression guard for finding A6 (REVISAO-FINAL.md), fixed by migration 0007
    (``glucose_records.notes_encrypted``).
    """
    patient = world.patient()
    note = f"sintoma privado {os.urandom(4).hex()}"
    created = patient.client.post(f"/api/patients/{patient.id}/glucose-records", json={
        "measured_at": "2026-06-05T08:00:00", "glucose_mg_dl": 140, "notes": note, "context_label": "unspecified",
    })
    assert created.status_code == 201, created.text
    blob = b"\x00".join(_as_bytes(value) for _, value in _all_cells("glucose_records"))
    assert note.encode() not in blob


def test_aut_ca_08_same_password_yields_distinct_non_reversible_hashes(world: World):
    """AUT-CA-08: equal passwords -> different hashes/salts; nothing decryptable."""
    from app.core.crypto import email_lookup, verify_password

    shared = world.new_password()
    first, second = world.patient(password=shared), world.doctor(password=shared)
    rows = {
        email: raw_execute("SELECT password_hash FROM user_accounts WHERE email_lookup = ?",
                           (email_lookup(email),))[0][0]
        for email in (first.email, second.email)
    }
    hash_a, hash_b = rows.values()
    assert hash_a != hash_b
    salts = []
    for stored in (hash_a, hash_b):
        algorithm, n, r, p, salt_hex, digest_hex = stored.split("$")
        assert algorithm == "scrypt" and int(n) >= 2**14 and int(r) >= 8 and int(p) >= 1
        assert len(bytes.fromhex(salt_hex)) >= 16 and len(bytes.fromhex(digest_hex)) >= 32
        assert shared not in stored and shared.encode().hex() not in stored
        assert verify_password(shared, stored) and not verify_password(shared + "x", stored)
        salts.append(salt_hex)
    assert salts[0] != salts[1]
    # Both accounts still log in with the shared password; nothing stores it reversibly.
    first.client.post("/api/auth/logout")
    assert first.login().status_code == 200


def test_aut_ca_22_tampered_or_transplanted_ciphertext_fails_safely(world: World):
    """AUT-CA-22: flipped ciphertext bytes or ciphertext moved between rows/contexts fail.

    Flip one byte of an encrypted field (e.g. doctor name) and swap a payload
    with another record's payload. Assert the read raises/returns a generic
    error: no tampered plaintext, no cryptographic detail in the response.
    """
    patient = world.patient()
    victim = world.doctor(display_name="Tamper Target Name")
    donor = world.doctor(display_name="Donor Doctor Name")
    ok = patient.client.get("/api/doctors/search", params={"short_id": victim.short_id})
    assert ok.status_code == 200 and ok.json()["doctor"]["name"] == "Tamper Target Name"

    original = raw_execute("SELECT name_encrypted FROM doctors WHERE id = ?", (victim.id,))[0][0]
    donor_payload = raw_execute("SELECT name_encrypted FROM doctors WHERE id = ?", (donor.id,))[0][0]
    flipped = bytearray(original)
    flipped[-1] ^= 0x01
    try:
        for label, payload in (("flipped", bytes(flipped)), ("transplanted", donor_payload)):
            raw_execute("UPDATE doctors SET name_encrypted = ? WHERE id = ?", (payload, victim.id))
            response = patient.client.get("/api/doctors/search", params={"short_id": victim.short_id})
            assert response.status_code >= 400, (label, response.text)
            for leaked in ("Donor Doctor Name", "Tamper Target Name", "InvalidTag", "cryptography",
                           "AESGCM", "Traceback", os.environ["MYGLICO_ENCRYPTION_KEY_V1"]):
                assert leaked not in response.text, (label, leaked)
    finally:
        raw_execute("UPDATE doctors SET name_encrypted = ? WHERE id = ?", (original, victim.id))
    restored = patient.client.get("/api/doctors/search", params={"short_id": victim.short_id})
    assert restored.json()["doctor"]["name"] == "Tamper Target Name"


def test_aad_binds_ciphertext_to_table_column_and_record():
    """AUT-CA-22 (supporting): AAD/context prevents cross-record reuse."""
    from cryptography.exceptions import InvalidTag

    from app.core.crypto import decrypt_field, encrypt_field

    context = {"table": "doctors", "column": "name", "record_id": "rec-1"}
    payload = encrypt_field("Bound Value", **context)
    assert decrypt_field(payload, **context) == "Bound Value"
    assert encrypt_field("Bound Value", **context) != payload  # fresh nonce per write
    for wrong in ({"table": "patients"}, {"column": "crm"}, {"record_id": "rec-2"}):
        with pytest.raises(InvalidTag):
            decrypt_field(payload, **{**context, **wrong})
    tampered = bytearray(payload)
    tampered[20] ^= 0xFF
    with pytest.raises(InvalidTag):
        decrypt_field(bytes(tampered), **context)
    with pytest.raises(ValueError):
        decrypt_field(b"not-a-payload", **context)


def test_aut_ca_23_and_cscw_ca_31_logs_and_api_payloads_carry_no_secrets_or_plaintext(
    world: World,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
):
    """AUT-CA-23 / CSCW-CA-31: no credentials, keys, clinical or message content in logs/API.

    Exercise register/login/link/message flows while capturing stdout/stderr,
    then assert no password, key material, e-mail, CRM or message text appears
    in the captured logs nor in error payloads.
    """
    caplog.set_level(logging.DEBUG)
    message_text = f"mensagem clinica {os.urandom(4).hex()}"
    title_text = f"titulo {os.urandom(4).hex()}"
    patient, doctor = world.patient(), world.doctor()
    link = world.active_link(patient, doctor)
    investigation = world.open_investigation(patient, doctor, title=title_text, message=message_text)
    reply = doctor.client.post(f"/api/investigations/{investigation['id']}/messages", json={"content": message_text + " r"})
    assert reply.status_code == 201

    bodies = []
    # error payloads: wrong password, duplicate registration, invalid body, foreign resource
    bodies.append(world.new_client().post("/api/auth/login", json={"email": patient.email, "password": "wrong-" + patient.password}))
    dup = world.register_payload("patient", email=patient.email, password=patient.password)
    bodies.append(world.new_client().post("/api/auth/register", json=dup))
    bad = {**world.register_payload("doctor", password=patient.password), "unexpected": message_text}
    bodies.append(world.new_client().post("/api/auth/register", json=bad))
    stranger = world.doctor()
    bodies.append(stranger.client.get(f"/api/investigations/{investigation['id']}"))
    bodies.append(stranger.client.post(f"/api/doctor-links/{link['id']}/revoke", json={"version": link["version"]}))
    # notification payloads never carry message/title content
    bodies.append(doctor.client.get("/api/notifications"))
    bodies.append(patient.client.get("/api/notifications"))
    bodies.append(patient.client.get("/api/auth/session"))

    for response in bodies[:5]:
        assert response.status_code >= 400
    captured = capsys.readouterr()
    haystacks = [captured.out, captured.err, caplog.text] + [r.text for r in bodies]
    secrets_to_hide = [patient.password, doctor.password, stranger.password,
                       os.environ["MYGLICO_ENCRYPTION_KEY_V1"], os.environ["MYGLICO_LOOKUP_HMAC_KEY"],
                       message_text, title_text, doctor.crm]
    for hay in haystacks:
        for secret in secrets_to_hide:
            assert secret not in hay
    # e-mails only ever appear for their owner's own session, never in errors/logs/notifications
    for hay in [captured.out, captured.err, caplog.text] + [r.text for r in bodies]:
        assert patient.email not in hay and doctor.email not in hay
    # keys never reach the HTTP surface through settings either
    assert world.new_client().get("/health").text.find(os.environ["MYGLICO_LOOKUP_HMAC_KEY"]) == -1


def test_lookup_index_uses_a_separate_key_from_encryption(world: World):
    """Supporting invariant: blind index key != encryption key (purpose separation)."""
    from app.core.config import get_settings
    from app.core.crypto import email_lookup, normalize_email

    settings = get_settings()
    assert settings.lookup_hmac_key and settings.encryption_key_v1
    assert settings.lookup_hmac_key != settings.encryption_key_v1

    patient = world.patient()
    stored = raw_execute("SELECT email_lookup FROM user_accounts WHERE email_lookup = ?",
                         (email_lookup(patient.email),))
    assert len(stored) == 1
    stored_lookup = stored[0][0]
    message = f"myglico:email:v1:{normalize_email(patient.email)}".encode()
    with_encryption_key = hmac.new(bytes.fromhex(settings.encryption_key_v1), message, hashlib.sha256).hexdigest()
    assert stored_lookup != with_encryption_key
    expected = hmac.new(bytes.fromhex(settings.lookup_hmac_key), message, hashlib.sha256).hexdigest()
    assert stored_lookup == expected
    assert stored_lookup != hashlib.sha256(normalize_email(patient.email).encode()).hexdigest()
