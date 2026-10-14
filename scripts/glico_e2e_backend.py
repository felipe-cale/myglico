"""Launch an isolated live backend and print seeded browser/API credentials.

Use from the repository root: python scripts/glico_e2e_backend.py --port 8012
Stop with Ctrl+C. The SQLite database is temporary and foreign keys are enabled.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import httpx
import uvicorn


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _account(base: str, role: str, email: str, password: str) -> dict:
    client = httpx.Client(base_url=base, timeout=10)
    payload = {"role": role, "email": email, "password": password,
               "password_confirmation": password, "display_name": f"E2E {role}",
               "privacy_notice_accepted": True}
    if role == "doctor":
        payload.update(crm=f"{uuid.uuid4().int % 100000000:08d}", uf="SP")
    response = client.post("/api/auth/register", json=payload)
    response.raise_for_status()
    cookie = response.cookies.get("myglico_session")
    if cookie:
        client.cookies.set("myglico_session", cookie)
    data = response.json()[role]
    return {"client": client, "email": email, "password": password, "id": data["id"],
            "short_id": data["short_id"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8012)
    parser.add_argument("--media", action="store_true",
                        help="enable photo/audio and spawn the local media worker (needs .venv-media and --models)")
    parser.add_argument("--models", default="tmp/media-f1/models-en")
    parser.add_argument("--worker-port", type=int, default=8400)
    args = parser.parse_args()
    temp_root = Path(tempfile.mkdtemp(prefix="myglico-glico-e2e-"))
    db_path = temp_root / "e2e.sqlite3"
    env = os.environ.copy()
    env.update({
        "MYGLICO_DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "MYGLICO_GLICO_ENABLED": "true",
        "MYGLICO_ENCRYPTION_KEY_V1": secrets.token_hex(32),
        "MYGLICO_LOOKUP_HMAC_KEY": secrets.token_hex(32),
        "MYGLICO_ACTIVE_ENCRYPTION_KEY_VERSION": "1",
        "MYGLICO_NOTIFICATION_DISPATCHER": "off",
        "MYGLICO_PROVENANCE_DIR": str(temp_root / "provenance"),
        "MYGLICO_RAW_DATA_DIR": str(temp_root / "raw"),
    })
    worker_proc = None
    if args.media:
        media_secret = secrets.token_hex(32)
        worker_python = ROOT / ".venv-media" / "Scripts" / "python.exe"
        if not worker_python.exists():
            worker_python = ROOT / ".venv-media" / "bin" / "python"
        worker_env = {**os.environ, "PADDLE_PDX_MODEL_SOURCE": "LOCAL", "HF_HUB_OFFLINE": "1",
                      "TRANSFORMERS_OFFLINE": "1", "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True"}
        worker_proc = subprocess.Popen([str(worker_python), str(ROOT / "scripts/media/run_local_worker.py"),
            "--models", str(ROOT / args.models), "--secret", media_secret, "--port", str(args.worker_port),
            *(["--whisper-dir", os.environ["GLICO_WHISPER_DIR"]] if os.environ.get("GLICO_WHISPER_DIR") else [])],
            cwd=ROOT, env=worker_env)
        env.update({
            "MYGLICO_GLICO_PHOTO_ENABLED": "true", "MYGLICO_GLICO_AUDIO_ENABLED": "true",
            "MYGLICO_GLICO_MEDIA_WORKER_URL": f"http://127.0.0.1:{args.worker_port}",
            "MYGLICO_GLICO_MEDIA_WORKER_SECRET": media_secret, "MYGLICO_GLICO_MEDIA_GLOBAL_JOBS": "2",
        })
    os.environ.update({key: value for key, value in env.items() if key.startswith("MYGLICO_")})
    migration = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT, env=env, capture_output=True, text=True)
    if migration.returncode:
        raise RuntimeError(migration.stderr or migration.stdout)

    # Import only after the isolated DB and secrets have been selected.
    from app.core.config import get_settings
    get_settings.cache_clear()
    from app.db.session import engine
    from sqlalchemy import text
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1

    config = uvicorn.Config("app.main:app", host=args.host, port=args.port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="glico-e2e-uvicorn", daemon=True)
    thread.start()
    base = f"http://{args.host}:{args.port}"
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            if httpx.get(base + "/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("backend did not become healthy")

    nonce = uuid.uuid4().hex[:12]
    patient = _account(base, "patient", f"glico-patient-{nonce}@example.test", secrets.token_urlsafe(18))
    doctor = _account(base, "doctor", f"glico-doctor-{nonce}@example.test", secrets.token_urlsafe(18))
    outsider = _account(base, "doctor", f"glico-outsider-{nonce}@example.test", secrets.token_urlsafe(18))
    link_response = patient["client"].post("/api/doctor-links", json={"doctor_short_id": doctor["short_id"]})
    link_response.raise_for_status()
    link = link_response.json()["link"]
    confirmed = doctor["client"].post(f"/api/doctor-links/{link['id']}/confirm", json={"version": link["version"]})
    confirmed.raise_for_status()
    for actor in (patient, doctor, outsider):
        actor["client"].close()
        del actor["client"]
    fixture = {"base_url": base, "sqlite_path": str(db_path), "foreign_keys": True,
        "patient": patient, "linked_doctor": doctor, "unlinked_doctor": outsider}
    print(json.dumps(fixture), flush=True)

    def stop_server(_signal, _frame):
        server.should_exit = True
    signal.signal(signal.SIGTERM, stop_server)
    try:
        while thread.is_alive():
            thread.join(timeout=0.5)
    except KeyboardInterrupt:
        server.should_exit = True
        thread.join(timeout=10)
    import shutil
    if worker_proc is not None:
        worker_proc.terminate()
    engine.dispose()
    shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
