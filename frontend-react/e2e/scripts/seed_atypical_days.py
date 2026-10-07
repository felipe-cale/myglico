"""Seed glucose readings for one patient and run the real analytics pipeline.

Used by the Playwright suite to produce atypical days deterministically. It
talks to the same disposable E2E database as the backend under test
(MYGLICO_DATABASE_URL + ephemeral keys inherited from playwright.config.mjs)
and calls the production code paths: GlucoseRecord rows + compute_analytics,
which is what the analytics worker/importer runs. Nothing is mocked.

Usage:
    python seed_atypical_days.py --patient-id <id> [--days 40]
        [--spikes 10,25] [--start 2026-06-01] [--global-run]
        [--midnight-day 5]

Prints a JSON object with the flagged dates and the run id.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patient-id", required=True)
    parser.add_argument("--days", type=int, default=40)
    parser.add_argument("--spikes", default="10,25")
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--global-run", action="store_true",
                        help="run analytics with patient_id=NULL, like the UCI importer does")
    parser.add_argument("--midnight-day", type=int, default=None,
                        help="offset of a day that also gets a 23:59 and a 00:01 reading")
    args = parser.parse_args()

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.entities import DailyIndicator, GlucoseRecord
    from app.services.analytics import compute_analytics

    start = date.fromisoformat(args.start)
    spikes = {int(value) for value in args.spikes.split(",") if value.strip()}
    with SessionLocal() as db:
        for offset in range(args.days):
            day = start + timedelta(days=offset)
            for reading in range(4):
                if offset in spikes:
                    value = 420.0 + reading * 15
                else:
                    value = 100.0 + ((offset * 7 + reading * 3) % 20)
                db.add(GlucoseRecord(
                    patient_id=args.patient_id,
                    measured_at=datetime.combine(day, datetime.min.time()) + timedelta(hours=6 + reading * 4),
                    glucose_mg_dl=value,
                ))
            if args.midnight_day is not None and offset == args.midnight_day:
                db.add(GlucoseRecord(patient_id=args.patient_id,
                                     measured_at=datetime.combine(day, datetime.min.time()) + timedelta(hours=23, minutes=59),
                                     glucose_mg_dl=111.0))
        db.commit()

    with SessionLocal() as db:
        run = compute_analytics(db, patient_id=None if args.global_run else args.patient_id,
                                trigger_type="e2e_seed")
        flagged = db.scalars(select(DailyIndicator).where(
            DailyIndicator.analysis_run_id == run.id,
            DailyIndicator.patient_id == args.patient_id,
            DailyIndicator.anomaly_flag.is_(True),
        ).order_by(DailyIndicator.indicator_date)).all()
        print(json.dumps({
            "run_id": run.id,
            "run_patient_id": run.patient_id,
            "flagged": [{"indicator_id": item.id, "date": item.indicator_date.isoformat()} for item in flagged],
        }))


if __name__ == "__main__":
    main()
