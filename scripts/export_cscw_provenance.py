"""Operator-only export of the CSCW provenance projection (PROV-JSON + Turtle).

Technical audit tool (SDD2 §10.6): it reads ``provenance_events`` with the
operator's own database credentials and has no HTTP endpoint. The output still
reveals who collaborated with whom, which is clinical metadata, so the
destination must be given explicitly and may not be any publicly served
directory (``artifacts/`` is mounted at ``/artifacts``; ``frontend-react/dist``
is the Vercel static output).

    python scripts/export_cscw_provenance.py --output /secure/audit/dir \
        [--patient-id <uuid>] [--since 2026-10-01T00:00:00] [--until 2026-10-08T00:00:00]
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import os
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class UnsafeOutputDir(ValueError):
    pass


def public_directories() -> list[Path]:
    from app.core.config import get_settings

    settings = get_settings()
    candidates = [
        ROOT_DIR / "artifacts",
        settings.artifacts_dir,
        settings.provenance_dir,
        ROOT_DIR / "frontend-react" / "public",
        ROOT_DIR / "frontend-react" / "dist",
    ]
    unique: list[Path] = []
    for candidate in candidates:
        resolved = Path(candidate).resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def validate_output_dir(output: str | Path) -> Path:
    if not str(output).strip():
        raise UnsafeOutputDir("--output must be an explicit directory")
    target = Path(output).expanduser().resolve()
    for public in public_directories():
        if target == public or public in target.parents:
            raise UnsafeOutputDir(
                f"Refusing to write CSCW provenance under a publicly served directory: {public}"
            )
    return target


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed  # provenance_events.occurred_at is stored as naive UTC


def _write_private(path: Path, content: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def export(output: str | Path, *, patient_id: str | None = None,
           since: datetime | None = None, until: datetime | None = None) -> tuple[Path, Path]:
    target = validate_output_dir(output)

    from app.db.session import SessionLocal
    from app.services.cscw_provenance import build_cscw_prov_document, serialize_cscw_prov

    target.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        document = build_cscw_prov_document(db, patient_id=patient_id, start=since, end=until)
    json_text, turtle = serialize_cscw_prov(document)
    stem = f"cscw-provenance-{patient_id}" if patient_id else "cscw-provenance"
    json_path = target / f"{stem}.json"
    ttl_path = target / f"{stem}.ttl"
    _write_private(json_path, json_text)
    _write_private(ttl_path, turtle)
    return json_path, ttl_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the CSCW provenance events as PROV-O (operator audit).")
    parser.add_argument("--output", required=True, help="Protected destination directory (never a public one).")
    parser.add_argument("--patient-id", help="Restrict the projection to one patient's events.")
    parser.add_argument("--since", help="Inclusive lower bound on occurred_at (ISO 8601; naive = UTC).")
    parser.add_argument("--until", help="Exclusive upper bound on occurred_at (ISO 8601; naive = UTC).")
    args = parser.parse_args(argv)
    try:
        json_path, ttl_path = export(args.output, patient_id=args.patient_id,
                                     since=_parse_utc(args.since), until=_parse_utc(args.until))
    except UnsafeOutputDir as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json_path)
    print(ttl_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
