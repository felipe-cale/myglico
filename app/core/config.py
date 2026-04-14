from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MYGLICO_", extra="ignore")

    app_name: str = "MyGlico MVP"
    app_env: str = "development"
    debug: bool = False
    database_url: str = Field(default=f"sqlite:///{(BASE_DIR / 'data' / 'myglico.db').as_posix()}")
    artifacts_dir: Path = BASE_DIR / "artifacts"
    provenance_dir: Path = BASE_DIR / "artifacts" / "provenance"
    semantic_dir: Path = BASE_DIR / "artifacts" / "semantic"
    raw_data_dir: Path = BASE_DIR / "data" / "raw"
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
    settings.provenance_dir.mkdir(parents=True, exist_ok=True)
    settings.semantic_dir.mkdir(parents=True, exist_ok=True)
    settings.raw_data_dir.mkdir(parents=True, exist_ok=True)
    return settings
