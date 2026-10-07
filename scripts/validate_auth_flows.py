"""Exercise account, session, access-control, and doctor search API flows in SQLite."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def main() -> None:
    env = os.environ.copy()
    env["MYGLICO_ENCRYPTION_KEY_V1"] = secrets.token_hex(32)
    env["MYGLICO_LOOKUP_HMAC_KEY"] = secrets.token_hex(32)

    with tempfile.TemporaryDirectory(prefix="myglico-auth-") as directory:
        database_path = Path(directory) / "auth.sqlite"
        env["MYGLICO_DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT_DIR,
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
        )

        os.environ.update(
            {
                "MYGLICO_DATABASE_URL": env["MYGLICO_DATABASE_URL"],
                "MYGLICO_ENCRYPTION_KEY_V1": env["MYGLICO_ENCRYPTION_KEY_V1"],
                "MYGLICO_LOOKUP_HMAC_KEY": env["MYGLICO_LOOKUP_HMAC_KEY"],
            }
        )

        from fastapi.testclient import TestClient

        from app.core.config import get_settings
        from app.core.rate_limit import reset_for_tests
        from app.main import app
        from app.db.session import SessionLocal, engine as app_engine
        from app.models.entities import UserAccount, UserSession
        from sqlalchemy import func, select

        get_settings.cache_clear()

        def register(client, *, role: str, email: str, display_name: str, **optional):
            return client.post(
                "/api/auth/register",
                json={
                    "role": role,
                    "email": email,
                    "password": "correct-horse-battery",
                    "password_confirmation": "correct-horse-battery",
                    "display_name": display_name,
                    **optional,
                },
            )

        with TestClient(app, base_url="https://myglico.test") as unauthenticated:
            invalid_role = unauthenticated.post(
                "/api/auth/register",
                json={
                    "role": "admin",
                    "email": "admin@example.test",
                    "password": "sentinel-secret-password",
                    "password_confirmation": "sentinel-secret-password",
                    "display_name": "Admin",
                },
            )
            assert invalid_role.status_code == 422
            assert "sentinel-secret-password" not in invalid_role.text
            # These historical clinical routes all require a live session.
            patient_list_response = unauthenticated.get("/api/patients")
            assert patient_list_response.status_code == 401
            assert patient_list_response.headers["cache-control"] == "no-store, private"
            assert unauthenticated.post("/api/patients", json={"name": "No account"}).status_code == 401
            assert unauthenticated.get("/api/patients/patient-a").status_code == 401
            assert unauthenticated.get(
                "/api/patients/patient-a/report.pdf?start_date=2026-01-01&end_date=2026-01-02"
            ).status_code == 401
            assert unauthenticated.post(
                "/api/patients/patient-a/glucose-records",
                json={"measured_at": "2026-01-01T12:00:00", "glucose_mg_dl": 120},
            ).status_code == 401
            assert unauthenticated.get("/api/doctors/search?short_id=ABC123").status_code == 401
            assert unauthenticated.get("/api/dashboard").status_code == 401
            assert unauthenticated.get("/api/auth/session").json() == {"authenticated": False}

        with TestClient(app, base_url="https://myglico.test") as patient_a:
            patient_a_registration = register(
                patient_a, role="patient", email="patient-a@example.test", display_name="Patient A"
            )
            assert patient_a_registration.status_code == 201, patient_a_registration.text
            patient_a_id = patient_a_registration.json()["patient"]["id"]
            patient_a_cookie = patient_a.cookies.get("myglico_session")
            assert patient_a_cookie and len(patient_a_cookie) >= 40
            set_cookie = patient_a_registration.headers["set-cookie"].lower()
            assert "httponly" in set_cookie and "secure" in set_cookie and "samesite=lax" in set_cookie
            assert patient_a.get("/api/auth/session").json()["patient"]["id"] == patient_a_id
            import app.services.auth_service as auth_service
            with patch.object(auth_service, "verify_password", wraps=auth_service.verify_password) as verifier:
                invalid_login = patient_a.post(
                    "/api/auth/login", json={"email": "unknown@example.test", "password": "wrong-password"}
                )
                assert verifier.call_count == 1 and verifier.call_args.args[1] == auth_service._DUMMY_PASSWORD_HASH
            assert invalid_login.status_code == 401
            assert invalid_login.json() == {"detail": "Invalid email or password."}
            assert patient_a.post("/api/auth/logout").status_code == 204
            assert patient_a.get("/api/auth/session").json() == {"authenticated": False}
            patient_a_login = patient_a.post(
                "/api/auth/login",
                json={"email": " PATIENT-A@example.test ", "password": "correct-horse-battery"},
            )
            assert patient_a_login.status_code == 200
            assert patient_a.get("/api/auth/session").json()["patient"]["id"] == patient_a_id
            assert patient_a.post("/api/auth/logout").status_code == 204

        with TestClient(app, base_url="https://myglico.test") as patient_b:
            patient_b_registration = register(
                patient_b, role="patient", email="patient-b@example.test", display_name="Patient B"
            )
            assert patient_b_registration.status_code == 201, patient_b_registration.text
            patient_b_id = patient_b_registration.json()["patient"]["id"]
            assert patient_b.post("/api/auth/logout").status_code == 204

        with TestClient(app, base_url="https://myglico.test") as doctor_client:
            doctor_registration = register(
                doctor_client,
                role="doctor",
                email="doctor@example.test",
                display_name="Doctor One",
                crm="12345",
                uf="sp",
            )
            assert doctor_registration.status_code == 201, doctor_registration.text
            doctor_registration_body = doctor_registration.json()
            doctor = doctor_registration_body["doctor"]
            doctor_id = doctor["id"]
            assert doctor_registration_body["account"]["roles"] == ["doctor"]
            assert doctor_client.get("/api/auth/session").json()["doctor"]["id"] == doctor_id
            assert doctor_client.post("/api/auth/logout").status_code == 204

            # A global email identity cannot acquire a second domain role.
            second_role = register(
                doctor_client, role="patient", email="doctor@example.test", display_name="Same person"
            )
            assert second_role.status_code == 409, second_role.text
            doctor_login = doctor_client.post(
                "/api/auth/login",
                json={"email": "doctor@example.test", "password": "correct-horse-battery"},
            )
            assert doctor_login.status_code == 200
            assert doctor_client.get("/api/auth/session").json()["doctor"]["id"] == doctor_id
            assert doctor_client.post("/api/auth/logout").status_code == 204

        with TestClient(app, base_url="https://myglico.test") as patient_a:
            assert patient_a.post(
                "/api/auth/login",
                json={"email": "patient-a@example.test", "password": "correct-horse-battery"},
            ).status_code == 200
            assert patient_a.get(f"/api/patients/{patient_b_id}").status_code == 404
            assert patient_a.post(
                f"/api/patients/{patient_b_id}/glucose-records",
                json={"measured_at": "2026-01-01T12:00:00", "glucose_mg_dl": 120},
            ).status_code == 404
            own_list = patient_a.get("/api/patients").json()
            assert own_list["count"] == 1 and [row["id"] for row in own_list["patients"]] == [patient_a_id]
            exact_detail = patient_a.get(f"/api/patients/{patient_a_id}?dates=2026-01-01,2026-01-03")
            assert exact_detail.status_code == 200, exact_detail.text
            assert patient_a.get(f"/api/patients/{patient_a_id}?dates=2026-1-1").status_code == 400
            short_id_search = patient_a.get(f"/api/doctors/search?short_id={doctor['short_id'].lower()}")
            doctor_search_body = short_id_search.json()
            assert short_id_search.status_code == 200
            assert set(doctor_search_body["doctor"]) == {
                "short_id",
                "name",
                "crm",
                "uf",
                "is_demo",
                "declared_verified",
                "link_status",
            }
            assert doctor_search_body["doctor"] == {
                "short_id": doctor["short_id"],
                "name": "Doctor One",
                "crm": "12345",
                "uf": "SP",
                "is_demo": False,
                "declared_verified": False,
                "link_status": "none",
            }
            crm_search = patient_a.get("/api/doctors/search?crm=12345&uf=SP")
            assert crm_search.status_code == 200 and crm_search.json() == doctor_search_body
            reset_for_tests()
            searches = [patient_a.get("/api/doctors/search?short_id=ZZZZZZ") for _ in range(31)]
            assert all(response.status_code == 200 for response in searches[:30])
            assert searches[-1].status_code == 429
            reset_for_tests()
            link_attempts = [patient_a.post(
                "/api/doctor-links", json={"doctor_short_id": doctor["short_id"]}
            ) for _ in range(11)]
            assert all(response.status_code != 429 for response in link_attempts[:10])
            assert link_attempts[-1].status_code == 429
            revoked_cookie_client = TestClient(app, base_url="https://myglico.test")
            revoked_cookie_client.cookies.set("myglico_session", patient_a.cookies.get("myglico_session"))
            assert revoked_cookie_client.get("/api/auth/session").json()["authenticated"] is True
            patient_a.post("/api/auth/logout")
            assert revoked_cookie_client.get("/api/auth/session").json() == {"authenticated": False}
            revoked_cookie_client.close()

        reset_for_tests()
        with TestClient(app, base_url="https://myglico.test") as limiter_client:
            attempts = [limiter_client.post(
                "/api/auth/login", json={"email": "missing@example.test", "password": "anything"}
            ) for _ in range(11)]
            assert all(response.status_code == 401 for response in attempts[:10])
            assert attempts[-1].status_code == 429

        with SessionLocal() as db:
            assert db.scalar(select(func.count(UserAccount.id))) == 3
            assert db.scalar(select(func.count(UserSession.id)).where(UserSession.revoked_at.is_(None))) == 0
        app_engine.dispose()

    print("PASS: patient and doctor register/login/session/logout; second role on an existing account is rejected; unauthenticated routes return 401; cross-patient access denied; doctor search is minimal.")


if __name__ == "__main__":
    main()
