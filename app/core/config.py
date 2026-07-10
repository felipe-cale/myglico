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
    semantic_dir: Path = _WRITABLE_DIR / "artifacts" / "semantic"
    raw_data_dir: Path = _WRITABLE_DIR / "data" / "raw"
    bootstrap_on_empty: bool = True
    default_hypo_threshold: float = 70.0
    pre_meal_min: float = 80.0
    pre_meal_max: float = 130.0
    generic_max: float = 180.0
    post_meal_max: float = 180.0
    semantic_base_uri: str = "https://myglico.local/resource/"
    semantic_vocab_uri: str = "https://myglico.local/vocab/"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    for directory in (settings.provenance_dir, settings.semantic_dir, settings.raw_data_dir):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Read-only deployment target (e.g. Vercel) without a writable /tmp
            # for this path, or the directory already exists read-only in the
            # deployment bundle. Reads of pre-generated artifacts still work;
            # skip rather than crash the whole app at import time.
            pass
    return settings
