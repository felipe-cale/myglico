from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal
from app.services.bootstrap import bootstrap_application


def main() -> None:
    with SessionLocal() as db:
        import_batch, analytics_run = bootstrap_application(db)
        if import_batch is not None:
            print(
                f"Import batch: {import_batch.id} "
                f"({import_batch.raw_record_count} raw / {import_batch.normalized_record_count} glucose records)"
            )
        if analytics_run is not None:
            print(f"Analytics run: {analytics_run.id} ({analytics_run.status})")


if __name__ == "__main__":
    main()
