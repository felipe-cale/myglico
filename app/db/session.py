from collections.abc import Generator
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


settings = get_settings()


def _build_engine(database_url: str):
    connect_args: dict = {}

    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    elif database_url.startswith("mysql"):
        # PyMySQL doesn't accept `ssl_mode`/`ssl-mode` (that's a mysql-connector-
        # python convention some managed providers document, e.g. Aiven). Strip
        # it out of the URL and translate it into the `ssl` connect arg PyMySQL
        # actually understands, so a copy-pasted provider connection string just
        # works instead of failing at connect time.
        parts = urlsplit(database_url)
        query = parse_qs(parts.query, keep_blank_values=True)
        ssl_mode = query.pop("ssl_mode", None) or query.pop("ssl-mode", None)
        if ssl_mode:
            connect_args["ssl"] = {}
            database_url = urlunsplit(parts._replace(query=urlencode(query, doseq=True)))

    return create_engine(database_url, connect_args=connect_args, future=True, pool_pre_ping=True)


engine = _build_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
