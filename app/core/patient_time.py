"""Patient-local calendar dates for naive UTC database timestamps."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_PATIENT_TIMEZONE = "America/Sao_Paulo"


def resolve_timezone(timezone_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name or DEFAULT_PATIENT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_PATIENT_TIMEZONE)


def patient_local_datetime(value: datetime, timezone_name: str | None) -> datetime:
    """Interpret naive stored datetimes as UTC and return the patient's wall time."""
    source = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return source.astimezone(resolve_timezone(timezone_name))


def patient_local_date(value: datetime, timezone_name: str | None) -> date:
    return patient_local_datetime(value, timezone_name).date()


def local_datetime_to_utc_naive(value: datetime, timezone_name: str | None) -> datetime:
    """Interpret naive input as patient wall time and return naive UTC for storage."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(tzinfo=resolve_timezone(timezone_name)).astimezone(timezone.utc).replace(tzinfo=None)


def local_date_utc_bounds(day: date, timezone_name: str | None) -> tuple[datetime, datetime]:
    """Return naive UTC bounds for a patient's local calendar day."""
    zone = resolve_timezone(timezone_name)
    start_local = datetime.combine(day, time.min, tzinfo=zone)
    end_local = datetime.combine(day.fromordinal(day.toordinal() + 1), time.min, tzinfo=zone)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def local_range_utc_bounds(
    start_date: date, end_date: date, timezone_name: str | None,
) -> tuple[datetime, datetime]:
    start, _ = local_date_utc_bounds(start_date, timezone_name)
    _, end = local_date_utc_bounds(end_date, timezone_name)
    return start, end
