"""Run the account migration against an isolated SQLite legacy-data fixture."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def main() -> None:
    env = os.environ.copy()
    env.setdefault("MYGLICO_ENCRYPTION_KEY_V1", secrets.token_hex(32))
    env.setdefault("MYGLICO_LOOKUP_HMAC_KEY", secrets.token_hex(32))

    with tempfile.TemporaryDirectory(prefix="myglico-migration-") as directory:
        database_path = Path(directory) / "legacy.sqlite"
        env["MYGLICO_DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        engine = create_engine(env["MYGLICO_DATABASE_URL"])
        with engine.begin() as connection:
            # Build the previous Patient/GlucoseRecord schema directly so this
            # exercises the migration's add-column path, not current metadata.
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES ('20260504_0002')")
            )
            connection.execute(
                text(
                    "CREATE TABLE patients (id VARCHAR(36) PRIMARY KEY, name VARCHAR(160) NOT NULL, "
                    "email VARCHAR(254) UNIQUE, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE glucose_records (id VARCHAR(36) PRIMARY KEY, patient_id VARCHAR(36) NOT NULL "
                    "REFERENCES patients(id), measured_at DATETIME NOT NULL, glucose_mg_dl FLOAT NOT NULL, "
                    "notes TEXT, "
                    "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
                )
            )
            connection.execute(text("CREATE INDEX ix_patients_name ON patients(name)"))
            # Minimal stand-ins for 0002 tables referenced by later foreign keys;
            # SQLite batch migrations reflect referenced tables and need them.
            connection.execute(text("CREATE TABLE provenance_events (id VARCHAR(36) PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE daily_indicators (id VARCHAR(36) PRIMARY KEY)"))
            connection.execute(
                text(
                    "INSERT INTO patients (id, name, email, created_at, updated_at) "
                    "VALUES (:id, :name, :email, :created_at, :updated_at)"
                ),
                {
                    "id": "patient-stable-id",
                    "created_at": "2026-10-06 00:00:00",
                    "updated_at": "2026-10-06 00:00:00",
                    "name": "Legacy Patient Name",
                    "email": "legacy@example.test",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO glucose_records (id, patient_id, measured_at, glucose_mg_dl, notes, created_at, updated_at) "
                    "VALUES ('record-stable-id', 'patient-stable-id', '2026-10-06 12:00:00', 112, 'Private clinical note', "
                    "'2026-10-06 12:00:00', '2026-10-06 12:00:00')"
                )
            )
        engine.dispose()

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT_DIR, env=env, check=True
        )

        from app.core.config import get_settings
        from app.core.crypto import decrypt_field

        os.environ["MYGLICO_ENCRYPTION_KEY_V1"] = env["MYGLICO_ENCRYPTION_KEY_V1"]
        os.environ["MYGLICO_LOOKUP_HMAC_KEY"] = env["MYGLICO_LOOKUP_HMAC_KEY"]
        get_settings.cache_clear()
        engine = create_engine(env["MYGLICO_DATABASE_URL"])
        with engine.connect() as connection:
            patient = connection.execute(
                text("SELECT id, name_encrypted, email_encrypted, short_id FROM patients WHERE id=:id"),
                {"id": "patient-stable-id"},
            ).one()
            record = connection.execute(
                text("SELECT id, patient_id, notes_encrypted FROM glucose_records WHERE id='record-stable-id'")
            ).one()
            columns = {column["name"] for column in inspect(connection).get_columns("patients")}
            glucose_columns = {column["name"] for column in inspect(connection).get_columns("glucose_records")}
            assert "name" not in columns and "email" not in columns
            assert patient.short_id and len(patient.short_id) == 6
            assert decrypt_field(patient.name_encrypted, table="patients", column="name", record_id=patient.id) == "Legacy Patient Name"
            assert decrypt_field(patient.email_encrypted, table="patients", column="email", record_id=patient.id) == "legacy@example.test"
            assert record.id == "record-stable-id" and record.patient_id == "patient-stable-id"
            assert "notes" not in glucose_columns and "notes_encrypted" in glucose_columns
            assert decrypt_field(record.notes_encrypted, table="glucose_records", column="notes", record_id=record.id) == "Private clinical note"
            assert b"Private clinical note" not in record.notes_encrypted
        engine.dispose()

    print("PASS: legacy patient identity and glucose notes encrypted, plaintext columns dropped, and Patient/GlucoseRecord IDs preserved.")


if __name__ == "__main__":
    main()
