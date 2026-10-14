"""Shared setup for the backend integration suite.

Isolation rules enforced here (PROMPT-ORCA.md, "Testes end-to-end e
evidÃªncias obrigatÃ³rias"):

* the suite always targets a dedicated SQLite file under ``data/`` (matched by
  the root ``.gitignore`` pattern ``data/*.db``) â€” never the dev/production
  URL. An explicit ``MYGLICO_INTEGRATION_DATABASE_URL`` can point the suite at
  another disposable database, but ``MYGLICO_DATABASE_URL`` from the shell is
  deliberately overridden so a dev/MySQL URL can never be reached by accident;
* key material is generated at runtime (or taken from the environment) and
  only lives in process env vars â€” no secret is written to a versioned file;
* provenance/raw-data directories point at a throw-away temp dir so the
  importer never writes into the versioned ``artifacts/`` tree;
* the env vars are set at conftest import time, *before* any ``app.*`` module
  is imported (``app.core.config.get_settings`` is ``lru_cache``d and
  ``app.db.session`` builds its engine at import). If something imported the
  app earlier with another database URL the run aborts instead of touching it.

Run with: ``pip install ".[test]" && python -m pytest tests/integration``.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_INTEGRATION_DB_FILE = REPO_ROOT / "data" / "integration.db"

INTEGRATION_DB_URL = os.environ.get(
    "MYGLICO_INTEGRATION_DATABASE_URL",
    f"sqlite:///{_DEFAULT_INTEGRATION_DB_FILE.as_posix()}",
)
# Rebuild/raw access must target the database the URL names, never a fixed path.
INTEGRATION_DB_FILE = (
    Path(INTEGRATION_DB_URL.removeprefix("sqlite:///"))
    if INTEGRATION_DB_URL.startswith("sqlite:///")
    else _DEFAULT_INTEGRATION_DB_FILE
)
_HEX_KEY = re.compile(r"^[0-9a-fA-F]{64}$")


def _hex_key_from_env(name: str) -> str:
    # app/core/crypto.py requires 32-byte keys encoded as 64 hex characters.
    current = os.environ.get(name, "")
    return current if _HEX_KEY.fullmatch(current) else secrets.token_hex(32)


_SCRATCH_DIR = Path(tempfile.mkdtemp(prefix="myglico-integration-"))

# Forced, not setdefault: a stray dev/production URL in the shell must never
# route integration tests at real data.
os.environ["MYGLICO_DATABASE_URL"] = INTEGRATION_DB_URL
os.environ["MYGLICO_ENCRYPTION_KEY_V1"] = _hex_key_from_env("MYGLICO_ENCRYPTION_KEY_V1")
os.environ["MYGLICO_LOOKUP_HMAC_KEY"] = _hex_key_from_env("MYGLICO_LOOKUP_HMAC_KEY")
os.environ["MYGLICO_ACTIVE_ENCRYPTION_KEY_VERSION"] = "1"
os.environ["MYGLICO_PROVENANCE_DIR"] = str(_SCRATCH_DIR / "provenance")
os.environ["MYGLICO_RAW_DATA_DIR"] = str(_SCRATCH_DIR / "raw")
os.environ.setdefault("MYGLICO_APP_ENV", "test")
os.environ.setdefault("MYGLICO_DEBUG", "false")
# Tests drive the outbox explicitly; no background drain racing assertions.
os.environ["MYGLICO_NOTIFICATION_DISPATCHER"] = "off"
os.environ["MYGLICO_GLICO_ENABLED"] = "true"

if "app.core.config" in sys.modules:
    sys.modules["app.core.config"].get_settings.cache_clear()
if "app.db.session" in sys.modules:
    _bound = sys.modules["app.db.session"].engine.url.render_as_string(hide_password=False)
    if _bound != INTEGRATION_DB_URL:
        raise pytest.UsageError(
            "app.db.session was imported before tests/integration/conftest.py with another "
            "database URL; run the integration suite in its own pytest process."
        )

TEST_EMAIL_DOMAIN = "integration.myglico.invalid"
BASE_URL = "https://testserver"  # session cookie is Secure


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_SCRATCH_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def prepared_database() -> Path:
    """Rebuild the isolated schema before the application imports its engine."""
    if not INTEGRATION_DB_URL.startswith("sqlite"):
        return Path(INTEGRATION_DB_URL)
    INTEGRATION_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = Path(f"{INTEGRATION_DB_FILE}{suffix}")
        if candidate.exists():
            candidate.unlink()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
        env=os.environ.copy(),
    )
    return INTEGRATION_DB_FILE


@pytest.fixture(scope="session")
def app(prepared_database: Path):
    from app.db.session import engine
    from app.main import app as fastapi_app

    assert engine.url.render_as_string(hide_password=False) == INTEGRATION_DB_URL, (
        "engine is not bound to the integration database"
    )
    yield fastapi_app
    engine.dispose()


@pytest.fixture(scope="session")
def client(app):
    from starlette.testclient import TestClient

    with TestClient(app, base_url=BASE_URL) as test_client:
        yield test_client


@pytest.fixture()
def db_session(prepared_database: Path, app):
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def raw_sqlite() -> sqlite3.Connection:
    """Direct connection to the file, bypassing the ORM (what a DB reader sees)."""
    connection = sqlite3.connect(INTEGRATION_DB_FILE, timeout=30)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


IS_SQLITE = INTEGRATION_DB_URL.startswith("sqlite")
_raw_engine = None


def raw_execute(sql: str, params: tuple = ()) -> list[tuple]:
    """Run SQL outside the ORM. Queries use SQLite's ``?`` placeholders."""
    if IS_SQLITE:
        conn = raw_sqlite()
        try:
            rows = conn.execute(sql, params).fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()
    global _raw_engine
    if _raw_engine is None:
        from sqlalchemy import create_engine

        _raw_engine = create_engine(INTEGRATION_DB_URL, future=True)
    conn = _raw_engine.raw_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql.replace("?", "%s"), params or None)
        rows = list(cursor.fetchall()) if cursor.description else []
        conn.commit()
        return rows
    finally:
        conn.close()


def table_columns(table: str) -> list[str]:
    if IS_SQLITE:
        return [row[1] for row in raw_execute(f"PRAGMA table_info({table})")]
    return [row[0] for row in raw_execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = ? ORDER BY ordinal_position",
        (table,),
    )]


def _create_failing_trigger(name: str, event: str, table: str, when: str, message: str) -> None:
    if IS_SQLITE:
        raw_execute(
            f"CREATE TRIGGER {name} BEFORE {event} ON {table} WHEN {when} "
            f"BEGIN SELECT RAISE(ABORT, '{message}'); END"
        )
    else:
        raw_execute(
            f"CREATE TRIGGER {name} BEFORE {event} ON {table} FOR EACH ROW BEGIN "
            f"IF {when} THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{message}'; END IF; END"
        )


@dataclass
class Actor:
    """One authenticated person with their own TestClient (own cookie jar)."""

    client: Any
    role: str
    email: str
    password: str = field(repr=False)
    display_name: str
    body: dict
    crm: str | None = None
    uf: str | None = None

    @property
    def domain(self) -> dict:
        return self.body[self.role]

    @property
    def id(self) -> str:
        return self.domain["id"]

    @property
    def short_id(self) -> str:
        return self.domain["short_id"]

    def login(self):
        return self.client.post("/api/auth/login", json={"email": self.email, "password": self.password})


class World:
    """Factory for actors and fixtures that drive the real API and database."""

    def __init__(self, app):
        self.app = app
        self._clients: list[Any] = []

    # -- clients / actors -------------------------------------------------
    def new_client(self):
        from starlette.testclient import TestClient

        # Each actor gets its own client address so the per-IP limiter (A5 fix)
        # treats actors independently, as real browsers on different hosts would.
        self._ip_counter = getattr(self, "_ip_counter", 0) + 1
        address = (f"10.{(id(self) >> 8) % 250}.{self._ip_counter // 250}.{self._ip_counter % 250 + 1}", 50000)
        raise_server_exceptions = os.environ.get("MYGLICO_INTEGRATION_RAISE_SERVER_EXCEPTIONS") == "true"
        client = TestClient(self.app, base_url=BASE_URL,
                            raise_server_exceptions=raise_server_exceptions, client=address)
        self._clients.append(client)
        return client

    @staticmethod
    def unique_email(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:12]}@{TEST_EMAIL_DOMAIN}"

    @staticmethod
    def new_password() -> str:
        return secrets.token_urlsafe(18)

    @staticmethod
    def new_crm() -> str:
        return f"{secrets.randbelow(10**8):08d}"

    def register_payload(self, role: str, *, email: str | None = None, password: str | None = None,
                         display_name: str | None = None, crm: str | None = None, uf: str | None = None) -> dict:
        password = password or self.new_password()
        payload = {
            "role": role,
            "email": email or self.unique_email(role),
            "password": password,
            "password_confirmation": password,
            "display_name": display_name or f"{role.title()} {uuid.uuid4().hex[:8]}",
            "privacy_notice_accepted": True,
        }
        if role == "doctor":
            payload["crm"] = crm or self.new_crm()
            payload["uf"] = uf or "SP"
        return payload

    def _register(self, role: str, **kwargs) -> Actor:
        client = self.new_client()
        payload = self.register_payload(role, **kwargs)
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 201, (response.status_code, response.text)
        return Actor(client=client, role=role, email=payload["email"], password=payload["password"],
                     display_name=payload["display_name"], body=response.json(),
                     crm=payload.get("crm"), uf=payload.get("uf"))

    def patient(self, **kwargs) -> Actor:
        return self._register("patient", **kwargs)

    def doctor(self, **kwargs) -> Actor:
        return self._register("doctor", **kwargs)

    # -- links / investigations -------------------------------------------
    @staticmethod
    def request_link(patient: Actor, doctor: Actor) -> dict:
        response = patient.client.post("/api/doctor-links", json={"doctor_short_id": doctor.short_id})
        assert response.status_code == 201, (response.status_code, response.text)
        return response.json()["link"]

    def active_link(self, patient: Actor, doctor: Actor) -> dict:
        link = self.request_link(patient, doctor)
        response = doctor.client.post(f"/api/doctor-links/{link['id']}/confirm", json={"version": link["version"]})
        assert response.status_code == 200, (response.status_code, response.text)
        return response.json()["link"]

    @staticmethod
    def open_investigation(opener: Actor, counterpart: Actor, *, event_id: str | None = None,
                           title: str = "Integration question", message: str = "Initial message") -> dict:
        body: dict[str, Any] = {"title": title, "initial_message": message}
        body["doctor_id" if opener.role == "patient" else "patient_id"] = counterpart.id
        if event_id:
            body["atypical_day_event_id"] = event_id
        response = opener.client.post("/api/investigations", json=body)
        assert response.status_code == 201, (response.status_code, response.text)
        return response.json()["investigation"]

    # -- direct data seeding ----------------------------------------------
    def seed_indicator(self, patient_id: str, indicator_date: date, *, anomaly: bool = True) -> str:
        from app.db.session import SessionLocal
        from app.models.entities import AnalysisRun, DailyIndicator

        with SessionLocal() as db:
            run = AnalysisRun(patient_id=patient_id, start_date=indicator_date, end_date=indicator_date,
                              status="completed", trigger_type="integration-test",
                              algorithm_name="daily_glycemic_summary", algorithm_version="test",
                              started_at=datetime.utcnow(), finished_at=datetime.utcnow())
            db.add(run)
            db.flush()
            indicator = DailyIndicator(analysis_run_id=run.id, patient_id=patient_id,
                                       indicator_date=indicator_date, glucose_event_count=5,
                                       avg_glucose=400.0 if anomaly else 110.0, anomaly_flag=anomaly,
                                       anomaly_score=-0.5 if anomaly else 0.1)
            db.add(indicator)
            db.commit()
            return indicator.id

    def seed_readings(self, patient_id: str, *, start: date = date(2026, 6, 1), days: int = 10,
                      extreme_offsets: tuple[int, ...] = (9,)) -> None:
        """Deterministic series: normal days at 105 mg/dL, extreme days at 480 mg/dL."""
        from app.db.session import SessionLocal
        from app.models.entities import GlucoseRecord

        with SessionLocal() as db:
            for offset in range(days):
                day = start + timedelta(days=offset)
                value = 480.0 if offset in extreme_offsets else 105.0
                for reading in range(5):
                    db.add(GlucoseRecord(
                        patient_id=patient_id,
                        measured_at=datetime.combine(day, datetime.min.time()) + timedelta(hours=reading * 3),
                        # Always labelled: see the NEW-1 note in test_idempotency_recompute_import.py
                        # (None mixed with labels crashes analytics under pandas 3).
                        glucose_mg_dl=value, context_label="unspecified",
                    ))
            db.commit()

    def compute(self, patient_id: str, trigger: str = "integration-test"):
        from app.db.session import SessionLocal
        from app.services.analytics import compute_analytics

        with SessionLocal() as db:
            run = compute_analytics(db, patient_id=patient_id, trigger_type=trigger)
            return run.id

    def atypical_patient(self, **kwargs) -> tuple[Actor, list[dict]]:
        """A registered patient whose analytics produced at least one atypical-day prompt."""
        patient = self.patient(**kwargs)
        self.seed_readings(patient.id)
        self.compute(patient.id)
        prompts = patient.client.get(f"/api/patients/{patient.id}/atypical-day-prompts").json()["prompts"]
        assert prompts, "deterministic fixture did not produce an atypical-day prompt"
        return patient, prompts

    # -- queries ------------------------------------------------------------
    @staticmethod
    def count(model, *criteria) -> int:
        from sqlalchemy import func, select

        from app.db.session import SessionLocal

        with SessionLocal() as db:
            return db.scalar(select(func.count()).select_from(model).where(*criteria)) or 0

    @staticmethod
    def events(activity: str | None = None, entity_id: str | None = None) -> list:
        from sqlalchemy import select

        from app.db.session import SessionLocal
        from app.models.entities import ProvenanceEvent

        query = select(ProvenanceEvent)
        if activity:
            query = query.where(ProvenanceEvent.activity_type == activity)
        if entity_id:
            query = query.where(ProvenanceEvent.entity_id == entity_id)
        with SessionLocal() as db:
            rows = list(db.scalars(query.order_by(ProvenanceEvent.occurred_at, ProvenanceEvent.id)))
            for row in rows:
                db.expunge(row)
            return rows

    @staticmethod
    def account_id(actor: Actor) -> str:
        from sqlalchemy import select

        from app.db.session import SessionLocal
        from app.models.entities import Doctor, Patient

        model = Patient if actor.role == "patient" else Doctor
        with SessionLocal() as db:
            return db.scalar(select(model.user_account_id).where(model.id == actor.id))

    @staticmethod
    @contextmanager
    def failing_insert(table: str, when: str = "1", message: str = "forced integration failure") -> Iterator[None]:
        """Install a trigger that aborts matching INSERTs for the duration of the block."""
        name = f"it_fail_{uuid.uuid4().hex[:10]}"
        _create_failing_trigger(name, "INSERT", table, when, message)
        try:
            yield
        finally:
            raw_execute(f"DROP TRIGGER IF EXISTS {name}")

    @staticmethod
    @contextmanager
    def failing_update(table: str, when: str = "1", message: str = "forced integration failure") -> Iterator[None]:
        name = f"it_failu_{uuid.uuid4().hex[:10]}"
        _create_failing_trigger(name, "UPDATE", table, when, message)
        try:
            yield
        finally:
            raw_execute(f"DROP TRIGGER IF EXISTS {name}")

    def close(self) -> None:
        for client in self._clients:
            client.close()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The in-process limiter is global state; each test starts with a fresh window."""
    try:
        from app.core.rate_limit import reset_for_tests
    except ImportError:  # limiter not present in this backend revision
        yield
        return
    reset_for_tests()
    yield
    reset_for_tests()


@pytest.fixture()
def world(app) -> Iterator[World]:
    instance = World(app)
    try:
        yield instance
    finally:
        instance.close()


def pytest_configure(config):
    # The backend uses datetime.utcnow() widely; keep the integration output readable.
    config.addinivalue_line("filterwarnings", "ignore::DeprecationWarning")

