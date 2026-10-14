from functools import lru_cache
from pathlib import Path
import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]

# Vercel's Python runtime ships a read-only filesystem except for /tmp, and that
# /tmp is wiped between cold starts. Serverless deploys never run the import/
# analytics scripts that write these directories, so redirecting them to /tmp
# just keeps settings load (and the /artifacts static mount) from crashing on
# import; it does not need to persist anything across requests there.
_ON_VERCEL = bool(os.environ.get("VERCEL"))
_WRITABLE_DIR = Path("/tmp/myglico") if _ON_VERCEL else BASE_DIR


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MYGLICO_", extra="ignore")

    app_name: str = "MyGlico MVP"
    app_env: str = "development"
    debug: bool = False
    database_url: str = Field(default=f"sqlite:///{(BASE_DIR / 'data' / 'myglico.db').as_posix()}")
    artifacts_dir: Path = BASE_DIR / "artifacts"
    provenance_dir: Path = _WRITABLE_DIR / "artifacts" / "provenance"
    raw_data_dir: Path = _WRITABLE_DIR / "data" / "raw"
    bootstrap_on_empty: bool = True
    default_hypo_threshold: float = 70.0
    pre_meal_min: float = 80.0
    pre_meal_max: float = 130.0
    generic_max: float = 180.0
    post_meal_max: float = 180.0
    semantic_base_uri: str = "https://myglico.local/resource/"
    semantic_vocab_uri: str = "https://myglico.local/vocab/"
    # Secrets are supplied by the deployment environment; no key material is
    # stored in settings files or the database. Keep old key versions during
    # rotation so existing payloads remain decryptable.
    active_encryption_key_version: int = 1
    encryption_key_v1: str | None = None
    encryption_key_v2: str | None = None
    lookup_hmac_key: str | None = None
    session_ttl_hours: int = Field(default=12, gt=0)
    glico_enabled: bool = False
    glico_photo_enabled: bool = False
    glico_audio_enabled: bool = False
    glico_external_language_enabled: bool = False
    glico_media_worker_url: str | None = None
    glico_media_worker_secret: str | None = None
    glico_media_global_jobs: int = Field(default=0, ge=0)
    # "loop" drains the notification outbox in a background task of a
    # long-running server; "off" leaves it to scripts/notification_outbox.py.
    # Serverless functions are frozen between invocations, so Vercel defaults
    # to "off".
    notification_dispatcher: str = Field(default="off" if _ON_VERCEL else "loop", pattern="^(loop|off)$")
    notification_dispatch_interval_seconds: float = Field(default=5.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    for directory in (settings.provenance_dir, settings.raw_data_dir):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Read-only deployment target (e.g. Vercel) without a writable /tmp
            # for this path, or the directory already exists read-only in the
            # deployment bundle. Reads of pre-generated artifacts still work;
            # skip rather than crash the whole app at import time.
            pass
    return settings
