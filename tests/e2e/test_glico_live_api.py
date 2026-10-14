from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import uuid

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SCRIPT = ROOT / "scripts" / "glico_e2e_backend.py"


@pytest.fixture(scope="module")
def live_backend():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.Popen([sys.executable, str(FIXTURE_SCRIPT), "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    try:
        line = process.stdout.readline()
        if not line:
            stderr = process.stderr.read()
            raise RuntimeError(f"live backend fixture exited ({process.poll()}): {stderr}")
        yield json.loads(line)
    finally:
        if process.poll() is None:
            process.terminate()  # exact child PID created by this fixture
            process.wait(timeout=20)
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()


def _login(fixture: dict, actor: dict) -> httpx.Client:
    client = httpx.Client(base_url=fixture["base_url"], timeout=10)
    response = client.post("/api/auth/login", json={"email": actor["email"], "password": actor["password"]})
    assert response.status_code == 200, response.text
    token = response.cookies.get("myglico_session")
    assert token
    # Requests over local HTTP do not send Secure cookies; retain the real session token for this loopback test.
    client.cookies.set("myglico_session", token)
    return client


def test_real_http_glico_review_commit_cancel_replay_and_authz(live_backend: dict):
    assert live_backend["foreign_keys"] is True
    patient = _login(live_backend, live_backend["patient"])
    outsider = _login(live_backend, live_backend["unlinked_doctor"])
    try:
        base_headers = {"origin": live_backend["base_url"]}
        csrf = patient.get("/api/glico/csrf")
        assert csrf.status_code == 200, csrf.text
        headers = {**base_headers, "x-myglico-csrf": csrf.json()["token"]}

        request_id = str(uuid.uuid4())
        created = patient.post("/api/glico/conversations", headers=headers, json={
            "locale": "pt-BR", "client_request_id": request_id})
        assert created.status_code == 201, created.text
        conversation = created.json()
        assert conversation["capabilities"] == {"text": True, "faq": True, "photo": False, "audio": False, "language_model": False}
        duplicate = patient.post("/api/glico/conversations", headers=headers, json={
            "locale": "pt-BR", "client_request_id": request_id})
        assert duplicate.status_code == 201, duplicate.text
        assert duplicate.json()["capabilities"] == conversation["capabilities"]

        message_id = str(uuid.uuid4())
        message_body = {"text": "128 mg/dL", "context_version": conversation["context_version"],
                        "client_request_id": message_id}
        message = patient.post(f"/api/glico/conversations/{conversation['id']}/messages",
                               headers=headers, json=message_body)
        assert message.status_code == 200, message.text
        assert message.json()["type"] == "proposal"
        replay = patient.post(f"/api/glico/conversations/{conversation['id']}/messages",
                              headers=headers, json=message_body)
        assert replay.status_code == 200, replay.text
        assert replay.json() == message.json()
        proposal = message.json()["proposal"]
        edited = patient.patch(f"/api/glico/proposals/{proposal['id']}", headers=headers, json={
            "version": proposal["version"], "context_version": conversation["context_version"],
            "fields": {"measured_at": "2026-10-13T08:30:00-03:00", "timezone": "America/Sao_Paulo"}})
        assert edited.status_code == 200, edited.text
        ready = edited.json()["proposal"]
        assert ready["version"] == proposal["version"] + 1 and ready["state"] == "READY"
        confirm_body = {"version": ready["version"], "context_version": conversation["context_version"],
                        "idempotency_key": str(uuid.uuid4())}
        confirmed = patient.post(f"/api/glico/proposals/{proposal['id']}/confirm", headers=headers,
                                 json=confirm_body)
        assert confirmed.status_code == 200, confirmed.text
        receipt = confirmed.json()["receipt"]
        assert receipt["result_type"] == "glucose_record"
        assert patient.post(f"/api/glico/proposals/{proposal['id']}/confirm", headers=headers,
                            json=confirm_body).json()["receipt"] == receipt

        second = patient.post(f"/api/glico/conversations/{conversation['id']}/messages", headers=headers, json={
            "text": "142 mg/dL", "context_version": conversation["context_version"],
            "client_request_id": str(uuid.uuid4())})
        assert second.status_code == 200 and second.json()["type"] == "proposal"
        cancelled = patient.post(f"/api/glico/proposals/{second.json()['proposal']['id']}/cancel", headers=headers,
                                 json={"version": second.json()["proposal"]["version"]})
        assert cancelled.status_code == 200 and cancelled.json()["state"] == "CANCELLED"
        assert patient.post(f"/api/glico/proposals/{second.json()['proposal']['id']}/cancel", headers=headers,
                            json={"version": second.json()["proposal"]["version"]}).json()["state"] == "CANCELLED"

        denied = outsider.get(f"/api/glico/conversations/{conversation['id']}")
        assert denied.status_code == 404
        denied_context = outsider.patch(f"/api/glico/conversations/{conversation['id']}/context",
            headers={"origin": live_backend["base_url"],
                     "x-myglico-csrf": outsider.get("/api/glico/csrf").json()["token"]},
            json={"version": 1, "patient_id": live_backend["patient"]["id"]})
        assert denied_context.status_code == 404

        connection = sqlite3.connect(live_backend["sqlite_path"])
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            record = connection.execute("SELECT id, glucose_mg_dl FROM glucose_records WHERE id=?",
                                        (receipt["result_id"],)).fetchone()
            assert record and record[1] == 128.0
            source = connection.execute("SELECT source_type, actor_user_id FROM glucose_record_sources WHERE glucose_record_id=?",
                                        (receipt["result_id"],)).fetchone()
            account_id = connection.execute("SELECT user_account_id FROM patients WHERE id=?",
                                            (live_backend["patient"]["id"],)).fetchone()[0]
            assert source == ("glico_text", account_id)
            event = connection.execute("SELECT activity_type, source_type FROM provenance_events WHERE entity_id=?",
                                       (receipt["result_id"],)).fetchone()
            assert event == ("glico_glucose_entry", "glico_text")
        finally:
            connection.close()
    finally:
        patient.close()
        outsider.close()
