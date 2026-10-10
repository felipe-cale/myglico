"""Drain the notification outbox outside the API request path.

The in-app inbox (`notifications`) is visible as soon as the producing
transaction commits; this only advances outbox bookkeeping and retries. Use it
where the API runs without the background loop (e.g. serverless deploys), or
from a scheduler.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.entities import NotificationOutbox
from app.services.notification_outbox import drain_notification_outbox


def _stats() -> dict[str, int]:
    with SessionLocal() as db:
        rows = db.execute(
            select(NotificationOutbox.status, func.count(NotificationOutbox.id))
            .group_by(NotificationOutbox.status)
        ).all()
    return {status: count for status, count in rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "stats"))
    parser.add_argument("--loop", action="store_true", help="Keep draining every --interval seconds.")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    if args.command == "stats":
        print(_stats())
        return
    while True:
        with SessionLocal() as db:
            print(drain_notification_outbox(db))
        if not args.loop:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
