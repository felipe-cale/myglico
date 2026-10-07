"""Validate explicit UCI demo provisioning in a disposable SQLite database."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="myglico-uci-demo-") as directory:
        test_dir = Path(directory)
        db_path = test_dir / "isolated.sqlite"
        os.environ.update(
            {
                "MYGLICO_DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
                "MYGLICO_ENCRYPTION_KEY_V1": secrets.token_hex(32),
                "MYGLICO_LOOKUP_HMAC_KEY": secrets.token_hex(32),
                "MYGLICO_PROVENANCE_DIR": str(test_dir / "provenance"),
                "MYGLICO_RAW_DATA_DIR": str(test_dir / "raw"),
            }
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT_DIR,
            env=os.environ.copy(),
            check=True,
            stdout=subprocess.DEVNULL,
        )

        from sqlalchemy import func, select

        from app.db.session import SessionLocal
        from app.models.entities import (
            AnalysisRun,
            DailyIndicator,
            DailyMetricsCurrent,
            DataSource,
            Doctor,
            GlucoseRecordSource,
            Patient,
            PatientDoctorLink,
            Notification,
            ProvenanceEvent,
            UserAccount,
        )
        from app.core.crypto import email_lookup, hash_password, verify_password
        from app.services.uci_importer import ExtractedDataset
        import app.services.uci_importer as importer
        import scripts.import_uci_diabetes as import_script

        fixture_root = test_dir / "dataset"
        fixture_root.mkdir()
        patient_file = fixture_root / "data-1"
        patient_file.write_text(
            "\n".join(
                [
                    "01-01-2024\t08:00\t58\t108",
                    "01-02-2024\t08:00\t58\t112",
                    "01-03-2024\t08:00\t58\t117",
                    "01-04-2024\t08:00\t58\t240",
                    "01-05-2024\t08:00\t58\t54",
                ]
            ),
            encoding="utf-8",
        )
        second_patient_file = fixture_root / "data-2"
        second_patient_file.write_text(patient_file.read_text(encoding="utf-8"), encoding="utf-8")
        fixture = ExtractedDataset(
            root_dir=fixture_root,
            patient_files=[patient_file, second_patient_file],
            data_codes_path=fixture_root / "Data-Codes",
            domain_description_path=fixture_root / "Domain-Description",
            zip_path=fixture_root / "fixture.zip",
        )
        importer.download_and_extract_dataset = lambda: fixture

        def snapshot() -> dict[str, object]:
            with SessionLocal() as db:
                return {
                    "patients": db.scalar(select(func.count(Patient.id))),
                    "accounts": db.scalar(select(func.count(UserAccount.id))),
                    "doctors": db.scalar(select(func.count(Doctor.id))),
                    "links": db.scalar(select(func.count(PatientDoctorLink.id))),
                    "demo_events": db.scalar(
                        select(func.count(ProvenanceEvent.id)).where(
                            ProvenanceEvent.activity_type == "DemoAssociationProvisioned"
                        )
                    ),
                    "record_sources": db.scalar(select(func.count(GlucoseRecordSource.id))),
                    "raw_records": db.scalar(select(func.count(GlucoseRecordSource.raw_import_record_id))),
                    "identity": tuple(
                        db.execute(
                            select(UserAccount.id, UserAccount.email_encrypted, UserAccount.password_hash)
                            .order_by(UserAccount.id)
                        ).all()
                    ),
                    "emails": tuple(
                        (account.email, account.password_hash)
                        for account in db.scalars(select(UserAccount).order_by(UserAccount.email_lookup)).all()
                    ),
                    "patient_emails": tuple(
                        (source.external_patient_code, source.patient.user_account.email)
                        for source in db.scalars(
                            select(importer.PatientSourceLink)
                            .where(importer.PatientSourceLink.data_source_id == db.scalar(
                                select(DataSource.id).where(DataSource.name == "UCI Diabetes")
                            ))
                            .order_by(importer.PatientSourceLink.external_patient_code)
                        ).all()
                    ),
                    "shortids": tuple(
                        db.execute(select(Patient.id, Patient.short_id, Patient.user_account_id).order_by(Patient.id)).all()
                    ),
                    "doctor_ids": tuple(db.execute(select(Doctor.id, Doctor.short_id).order_by(Doctor.id)).all()),
                    "link_ids": tuple(
                        db.execute(
                            select(PatientDoctorLink.id, PatientDoctorLink.status).order_by(PatientDoctorLink.id)
                        ).all()
                    ),
                    "event_ids": tuple(
                        db.scalars(
                            select(ProvenanceEvent.id).where(
                                ProvenanceEvent.activity_type == "DemoAssociationProvisioned"
                            ).order_by(ProvenanceEvent.id)
                        ).all()
                    ),
                    "analysis_runs": db.scalar(select(func.count(AnalysisRun.id))),
                    "indicators": db.scalar(select(func.count(DailyIndicator.id))),
                    "daily_metrics": db.scalar(select(func.count(DailyMetricsCurrent.id))),
                    "atypical_notifications": db.scalar(select(func.count(Notification.id)).where(
                        Notification.notification_type == "atypical_day_prompt",
                    )),
                }

        import_script.main([])
        # The regular importer remains data-only unless the demo option is explicit.
        with SessionLocal() as db:
            assert db.scalar(select(func.count(UserAccount.id))) == 0
            assert db.scalar(select(func.count(Doctor.id))) == 0
            assert db.scalar(select(func.count(PatientDoctorLink.id))) == 0

        import_script.main(["--provision-demo-accounts"])
        first = snapshot()
        assert first["patients"] == 2 and first["accounts"] == 3 and first["doctors"] == 1
        assert first["links"] == 2 and first["demo_events"] == 2
        assert first["record_sources"] == 10 and first["raw_records"] == 10
        assert first["patient_emails"] == (("uci-1", "patient1@demo.myglico.invalid"), ("uci-2", "patient2@demo.myglico.invalid"))
        assert {email for email, _ in first["emails"]} == {
            "doctor@demo.myglico.invalid", "patient1@demo.myglico.invalid", "patient2@demo.myglico.invalid"
        }
        assert all(verify_password("qwerty", password_hash) for _, password_hash in first["emails"])
        assert first["analysis_runs"] >= 1 and first["indicators"] >= 1 and first["daily_metrics"] >= 1
        assert first["atypical_notifications"] <= first["patients"], \
            "analytics should batch atypical invitations to at most one notice per patient"
        with SessionLocal() as db:
            demo_patients = db.scalars(select(Patient).order_by(Patient.id)).all()
            for patient in demo_patients:
                notices = db.scalars(select(Notification).where(
                    Notification.recipient_user_account_id == patient.user_account_id,
                    Notification.notification_type == "atypical_day_prompt",
                )).all()
                assert len(notices) <= 1
                if notices:
                    assert notices[0].payload.get("dates") and notices[0].payload.get("count") >= 1

        import_script.main(["--provision-demo-accounts"])
        second = snapshot()
        assert first == second, "A second demo import changed persisted identities, links, events, readings, or analytics"

        from fastapi.testclient import TestClient
        from app.main import app

        for demo_email in ("patient1@demo.myglico.invalid", "patient2@demo.myglico.invalid", "doctor@demo.myglico.invalid"):
            with TestClient(app, base_url="https://myglico.test") as client:
                login = client.post("/api/auth/login", json={"email": demo_email, "password": "qwerty"})
                assert login.status_code == 200, login.text
                assert client.get("/api/auth/session").json()["authenticated"] is True
                assert client.post("/api/auth/logout").status_code == 204

        # Provisioning must not rewrite a pre-existing account's credentials.
        with SessionLocal() as db:
            account = db.scalar(select(UserAccount).where(UserAccount.email_lookup == email_lookup("patient1@demo.myglico.invalid")))
            preserved_hash = hash_password("owner-managed-password")
            account.password_hash = preserved_hash
            db.commit()
        import_script.main(["--provision-demo-accounts"])
        with SessionLocal() as db:
            account = db.scalar(select(UserAccount).where(UserAccount.email_lookup == email_lookup("patient1@demo.myglico.invalid")))
            assert account.email == "patient1@demo.myglico.invalid"
            assert account.password_hash == preserved_hash

        with SessionLocal() as db:
            link = db.scalar(select(PatientDoctorLink))
            link.status = "REVOKED"
            link.revoked_at = datetime.utcnow()
            link.revoked_by_role = "PATIENT"
            link.open_pair_key = None
            db.commit()
        import_script.main(["--provision-demo-accounts"])
        with SessionLocal() as db:
            link = db.scalar(select(PatientDoctorLink))
            assert link.status == "REVOKED", "Rerunning demo provisioning reactivated a revoked link"
            assert db.scalar(
                select(func.count(ProvenanceEvent.id)).where(
                    ProvenanceEvent.activity_type == "DemoAssociationProvisioned"
                )
            ) == 2

        print(
            "PASS: patientN@demo.myglico.invalid and doctor@demo.myglico.invalid log in with qwerty; "
            "re-import preserved existing credentials, IDs, SHORTIDs, links, provenance, readings and analytics; "
            "a revoked demo link stayed revoked."
        )
        SessionLocal.kw["bind"].dispose()


if __name__ == "__main__":
    main()
