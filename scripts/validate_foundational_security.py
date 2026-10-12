"""Demonstrate encrypted-at-rest fields, salted password hashes, and SHORTID retries.

Run with MYGLICO_ENCRYPTION_KEY_V1 and MYGLICO_LOOKUP_HMAC_KEY set. The script
creates and removes a temporary SQLite database; it never touches the app DB.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.crypto import (
    crm_uf_lookup,
    email_lookup,
    encrypt_field,
    generate_short_id,
    hash_password,
    verify_password,
)
from app.db.base import Base
from app.models.entities import Doctor, Patient, UserAccount


def main() -> None:
    if not os.environ.get("MYGLICO_ENCRYPTION_KEY_V1") or not os.environ.get("MYGLICO_LOOKUP_HMAC_KEY"):
        raise SystemExit("Set MYGLICO_ENCRYPTION_KEY_V1 and MYGLICO_LOOKUP_HMAC_KEY to 64-character hex keys.")

    first_hash = hash_password("validation-only-password")
    second_hash = hash_password("validation-only-password")
    assert first_hash != second_hash
    assert verify_password("validation-only-password", first_hash)
    assert not verify_password("wrong-password", first_hash)
    assert email_lookup("  Person@Example.Test ") == email_lookup("person@example.test")
    assert crm_uf_lookup("CRM 12345", " sp ") == crm_uf_lookup("crm 12345", "SP")

    collision_checks = 0

    def simulate_collision(_: str) -> bool:
        nonlocal collision_checks
        collision_checks += 1
        return collision_checks == 1

    unique_after_retry = generate_short_id(simulate_collision)
    assert len(unique_after_retry) == 6 and collision_checks == 2

    with tempfile.TemporaryDirectory(prefix="myglico-crypto-") as temporary_directory:
        db_path = Path(temporary_directory) / "isolated.sqlite"
        engine = create_engine(f"sqlite:///{db_path.as_posix()}")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            account = UserAccount(
                email="private.account@example.test",
                password_hash=first_hash,
                account_status="active",
                is_demo=False,
            )
            patient = Patient(name="Private Patient Name", email="private.patient@example.test")
            doctor_id = "5ab7a88a-e318-4b09-b751-1db6dcb912d2"
            doctor = Doctor(
                id=doctor_id,
                short_id=generate_short_id(),
                user_account=account,
                name_encrypted=encrypt_field(
                    "Private Doctor Name", table="doctors", column="name", record_id=doctor_id
                ),
                crm_encrypted=encrypt_field("CRM 12345", table="doctors", column="crm", record_id=doctor_id),
                uf_encrypted=encrypt_field("SP", table="doctors", column="uf", record_id=doctor_id),
                crm_uf_lookup=crm_uf_lookup("CRM 12345", "SP"),
                is_demo=False,
                declared_verified=False,
            )
            session.add_all([account, patient, doctor])
            session.commit()
            assert patient.name == "Private Patient Name"
            assert patient.email == "private.patient@example.test"
            assert patient.source_file == "manual"
            assert account.email == "private.account@example.test"
            patient_id = patient.id
            account_id = account.id

        with closing(sqlite3.connect(db_path)) as raw_db:
            raw_db.execute("PRAGMA foreign_keys=ON")
            patient_row = raw_db.execute(
                "SELECT name_encrypted, email_encrypted FROM patients WHERE id=?", (patient_id,)
            ).fetchone()
            account_row = raw_db.execute(
                "SELECT email_encrypted FROM user_accounts WHERE id=?", (account_id,)
            ).fetchone()
            doctor_row = raw_db.execute(
                "SELECT name_encrypted, crm_encrypted, uf_encrypted FROM doctors WHERE id=?", (doctor_id,)
            ).fetchone()
            stored_values = [value for row in (patient_row, account_row, doctor_row) for value in row if value]
            assert all(isinstance(value, bytes) for value in stored_values)
            forbidden = [
                b"Private Patient Name",
                b"private.patient@example.test",
                b"private.account@example.test",
                b"Private Doctor Name",
                b"CRM 12345",
                b"SP",
            ]
            assert all(secret not in b"".join(stored_values) for secret in forbidden)

        engine.dispose()

    print("PASS: direct SQLite columns contain ciphertext; per-password salts differ; SHORTID retries collisions.")


if __name__ == "__main__":
    main()
