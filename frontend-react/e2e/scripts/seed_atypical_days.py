"""Seed glucose readings for one patient and run the real analytics pipeline.

Used by the Playwright suite to produce atypical days deterministically. It
talks to the same disposable E2E database as the backend under test
(MYGLICO_DATABASE_URL + ephemeral keys inherited from playwright.config.mjs)
and calls the production code paths: GlucoseRecord rows + compute_analytics,
which is what the analytics worker/importer runs. Nothing is mocked.

Usage:
    python seed_atypical_days.py --patient-id <id> [--days 40]
        [--spikes 10,25] [--start 2026-06-01] [--global-run]

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
    parser.add_argument("--flatten-date", default=None,
                        help="YYYY-MM-DD whose existing readings are corrected to a normal value before reprocessing")
    args = parser.parse_args()

    from sqlalchemy import select

    from app.core.patient_time import local_date_utc_bounds, local_datetime_to_utc_naive
    from app.db.session import SessionLocal
    from app.models.entities import DailyIndicator, GlucoseRecord, Patient
    from app.services.analytics import compute_analytics

    start = date.fromisoformat(args.start)
    spikes = {int(value) for value in args.spikes.split(",") if value.strip()}
    with SessionLocal() as db:
        patient = db.get(Patient, args.patient_id)
        if patient is None:
            raise SystemExit(f"patient not found: {args.patient_id}")
        for offset in range(args.days):
            day = start + timedelta(days=offset)
            for reading in range(4):
                if offset in spikes:
                    value = 420.0 + reading * 15
                else:
                    value = 100.0 + ((offset * 7 + reading * 3) % 20)
                local_time = datetime.combine(day, datetime.min.time()) + timedelta(hours=6 + reading * 4)
                db.add(GlucoseRecord(
                    patient_id=args.patient_id,
                    measured_at=local_datetime_to_utc_naive(local_time, patient.timezone),
                    glucose_mg_dl=value,
                ))
        if args.flatten_date:
            # Corrects an already-flagged day (stored naive UTC, patient wall date) so the
            # next run drops its atypical classification, as in CSCW-CA-22.
            flat_day = date.fromisoformat(args.flatten_date)
            day_start, day_end = local_date_utc_bounds(flat_day, patient.timezone)
            # Copy the previous day's readings: a constant value would itself look atypical.
            previous = {
                record.measured_at + timedelta(days=1): record.glucose_mg_dl
                for record in db.scalars(select(GlucoseRecord).where(
                    GlucoseRecord.patient_id == args.patient_id,
                    GlucoseRecord.measured_at >= day_start - timedelta(days=1),
                    GlucoseRecord.measured_at < day_start,
                ))
            }
            for record in db.scalars(select(GlucoseRecord).where(
                GlucoseRecord.patient_id == args.patient_id,
                GlucoseRecord.measured_at >= day_start,
                GlucoseRecord.measured_at < day_end,
            )):
                record.glucose_mg_dl = previous.get(record.measured_at, 110.0)
        db.commit()

    with SessionLocal() as db:
        if args.global_run:
            # A patient_id=NULL run, like the UCI importer's, bounded to the seeded
            # window. Unbounded, it would recompute every patient left in the shared
            # E2E database by earlier tests: its runtime grows with the suite (P2-03)
            # and it would become the newest run of all of those patients.
            window_end = start + timedelta(days=max(args.days, 1) - 1)
            run = compute_analytics(db, patient_id=None, start_date=start, end_date=window_end,
                                    trigger_type="e2e_seed")
        else:
            run = compute_analytics(db, patient_id=args.patient_id, trigger_type="e2e_seed")
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
