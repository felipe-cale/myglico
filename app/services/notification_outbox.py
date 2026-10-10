"""Minimal durable dispatcher for the in-app notification inbox."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.entities import Notification, NotificationOutbox, UserAccount


logger = logging.getLogger(__name__)


def _deliver_to_in_app_inbox(db: Session, notification: Notification) -> None:
    """Confirm the already-committed notification has a valid inbox owner."""
    if db.get(UserAccount, notification.recipient_user_account_id) is None:
        raise LookupError("notification recipient unavailable")


def drain_notification_outbox(
    db: Session, *, limit: int = 100, now: datetime | None = None,
) -> dict[str, int]:
    """Process due notifications, persisting delivery state and retry metadata.

    The notification row is the durable in-app inbox entry. The outbox
    consumer acknowledges it after verifying its recipient. Delivery failures
    stay visible on the row and are retried with capped exponential backoff.
    """
    current_time = now or datetime.utcnow()
    rows = db.scalars(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.status == "PENDING",
            or_(NotificationOutbox.next_attempt_at.is_(None),
                NotificationOutbox.next_attempt_at <= current_time),
        )
        .order_by(NotificationOutbox.created_at, NotificationOutbox.id)
        .limit(max(1, min(limit, 500)))
        .with_for_update(skip_locked=True)
    ).all()
    delivered = 0
    failed = 0
    for outbox in rows:
        notification = db.get(Notification, outbox.notification_id)
        outbox.attempts += 1
        try:
            if notification is None:
                raise LookupError("notification record unavailable")
            _deliver_to_in_app_inbox(db, notification)
        except Exception as exc:
            failed += 1
            delay_seconds = min(2 ** min(outbox.attempts - 1, 8), 300)
            outbox.status = "PENDING"
            outbox.next_attempt_at = current_time + timedelta(seconds=delay_seconds)
            # Store only the exception class; exception text may contain user data.
            outbox.last_error = type(exc).__name__[:120]
            logger.warning(
                "Notification outbox delivery failed",
                extra={"outbox_id": outbox.id, "attempt": outbox.attempts,
                       "error_type": outbox.last_error},
            )
        else:
            delivered += 1
            outbox.status = "DELIVERED"
            outbox.processed_at = current_time
            outbox.next_attempt_at = None
            outbox.last_error = None
    db.commit()
    return {"delivered": delivered, "failed": failed, "processed": len(rows)}
