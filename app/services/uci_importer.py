from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile
import calendar
import re
import shutil
import tarfile

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from unlzw3 import unlzw

from app.core.config import get_settings
from app.models.entities import DataQualityIssue, ImportBatch, NormalizedEvent, Patient, RawEvent


settings = get_settings()
UCI_DIABETES_URL = "https://archive.ics.uci.edu/static/public/34/diabetes.zip"
SLOT_TIMES = {"08:00": "breakfast", "12:00": "lunch", "18:00": "dinner", "22:00": "bedtime"}

CODEBOOK: dict[int, dict[str, str | bool]] = {
    33: {"event_type": "insulin_dose", "event_subtype": "regular"},
    34: {"event_type": "insulin_dose", "event_subtype": "nph"},
    35: {"event_type": "insulin_dose", "event_subtype": "ultralente"},
    48: {"event_type": "glucose_measurement", "event_subtype": "unspecified", "is_glucose": True},
    57: {"event_type": "glucose_measurement", "event_subtype": "unspecified", "is_glucose": True},
    58: {"event_type": "glucose_measurement", "event_subtype": "pre_breakfast", "is_glucose": True},
    59: {"event_type": "glucose_measurement", "event_subtype": "post_breakfast", "is_glucose": True},
    60: {"event_type": "glucose_measurement", "event_subtype": "pre_lunch", "is_glucose": True},
    61: {"event_type": "glucose_measurement", "event_subtype": "post_lunch", "is_glucose": True},
    62: {"event_type": "glucose_measurement", "event_subtype": "pre_supper", "is_glucose": True},
    63: {"event_type": "glucose_measurement", "event_subtype": "post_supper", "is_glucose": True},
    64: {"event_type": "glucose_measurement", "event_subtype": "pre_snack", "is_glucose": True},
    65: {"event_type": "symptom", "event_subtype": "hypoglycemic_symptom"},
    66: {"event_type": "meal", "event_subtype": "typical_meal"},
    67: {"event_type": "meal", "event_subtype": "more_than_usual_meal"},
    68: {"event_type": "meal", "event_subtype": "less_than_usual_meal"},
    69: {"event_type": "exercise", "event_subtype": "typical_exercise"},
    70: {"event_type": "exercise", "event_subtype": "more_than_usual_exercise"},
    71: {"event_type": "exercise", "event_subtype": "less_than_usual_exercise"},
    72: {"event_type": "special_event", "event_subtype": "unspecified_special_event"},
}


@dataclass(slots=True)
class ExtractedDataset:
    root_dir: Path
    patient_files: list[Path]
    data_codes_path: Path
    domain_description_path: Path
    zip_path: Path


def dataset_already_loaded(db: Session) -> bool:
    return db.scalar(select(func.count(Patient.id))) > 0


def download_and_extract_dataset() -> ExtractedDataset:
    raw_dir = settings.raw_data_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / "uci_diabetes.zip"
    extract_dir = raw_dir / "uci_diabetes"

    if not zip_path.exists():
        response = requests.get(UCI_DIABETES_URL, timeout=60)
        response.raise_for_status()
        zip_path.write_bytes(response.content)

    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    with ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)

    compressed_tar = extract_dir / "diabetes-data.tar.Z"
    tar_path = extract_dir / "diabetes-data.tar"
    tar_path.write_bytes(unlzw(compressed_tar.read_bytes()))

    with tarfile.open(tar_path) as tar:
        tar.extractall(extract_dir)

    dataset_root = extract_dir / "Diabetes-Data"
    patient_files = sorted(path for path in dataset_root.glob("data-*") if re.fullmatch(r"data-\d+", path.name))
    return ExtractedDataset(
        root_dir=dataset_root,
        patient_files=patient_files,
        data_codes_path=dataset_root / "Data-Codes",
        domain_description_path=dataset_root / "Domain-Description",
        zip_path=zip_path,
    )


def _parse_datetime(raw_date: str, raw_time: str) -> tuple[datetime, str | None]:
    try:
        return datetime.strptime(f"{raw_date} {raw_time}", "%m-%d-%Y %H:%M"), None
    except ValueError:
        month, day, year = [int(part) for part in raw_date.split("-")]
        hour, minute = [int(part) for part in raw_time.split(":")]
        safe_day = min(day, calendar.monthrange(year, month)[1])
        safe_hour = min(hour, 23)
        safe_minute = min(minute, 59)
        corrected = datetime(year, month, safe_day, safe_hour, safe_minute)
        return corrected, f"Timestamp coerced from '{raw_date} {raw_time}' to '{corrected.isoformat(sep=' ')}'."


def _coerce_numeric_value(raw_value: str) -> tuple[float, str | None]:
    try:
        return float(raw_value), None
    except ValueError:
        match = re.search(r"[-+]?\d+(?:\.\d+)?", raw_value)
        if match:
            return float(match.group()), f"Numeric value coerced from raw token '{raw_value}'."
        return 0.0, f"Numeric value could not be parsed from raw token '{raw_value}'; defaulted to 0."


def _normalize_event(raw_date: str, raw_time: str, raw_code: int, raw_value: str) -> dict[str, object]:
    metadata = CODEBOOK.get(raw_code)
    numeric_value, coercion_note = _coerce_numeric_value(raw_value)
    matches_slot_time = raw_time in SLOT_TIMES
    timestamp_quality = "slot_aligned" if matches_slot_time else "recorded"

    if metadata is None:
        return {
            "event_type": "unknown",
            "event_subtype": "unknown",
            "numeric_value": numeric_value,
            "glucose_mg_dl": None,
            "insulin_units": None,
            "context_label": None,
            "meal_size": None,
            "exercise_level": None,
            "symptom_label": None,
            "special_event_label": None,
            "is_glucose": False,
            "matches_slot_time": matches_slot_time,
            "timestamp_quality": timestamp_quality,
            "quality_note": "Unknown UCI code encountered during normalization.",
        }

    event_type = str(metadata["event_type"])
    event_subtype = str(metadata["event_subtype"])
    notes = []
    if matches_slot_time:
        notes.append("Timestamp aligns with canonical slot time; record may originate from paper log slots.")
    if coercion_note:
        notes.append(coercion_note)
    return {
        "event_type": event_type,
        "event_subtype": event_subtype,
        "numeric_value": numeric_value,
        "glucose_mg_dl": numeric_value if bool(metadata.get("is_glucose", False)) else None,
        "insulin_units": numeric_value if event_type == "insulin_dose" else None,
        "context_label": event_subtype if event_type == "glucose_measurement" else None,
        "meal_size": event_subtype if event_type == "meal" else None,
        "exercise_level": event_subtype if event_type == "exercise" else None,
        "symptom_label": event_subtype if event_type == "symptom" else None,
        "special_event_label": event_subtype if event_type == "special_event" else None,
        "is_glucose": bool(metadata.get("is_glucose", False)),
        "matches_slot_time": matches_slot_time,
        "timestamp_quality": timestamp_quality,
        "quality_note": " ".join(notes) if notes else None,
    }


def import_uci_diabetes(db: Session) -> tuple[ImportBatch, ExtractedDataset]:
    dataset = download_and_extract_dataset()
    import_batch = ImportBatch(
        source_name="UCI Diabetes",
        source_url=UCI_DIABETES_URL,
        source_version="UCI-34",
        status="running",
        notes=(
            "MVP import for MyGlico using the UCI Diabetes outpatient monitoring dataset. "
            "The source mixes device timestamps and paper log logical slots."
        ),
    )
    db.add(import_batch)
    db.flush()

    raw_count = 0
    normalized_count = 0

    for patient_file in dataset.patient_files:
        patient_suffix = patient_file.name.split("-")[-1]
        patient = Patient(
            source_patient_code=f"uci-{patient_suffix}",
            display_name=f"Paciente UCI {patient_suffix}",
            source_file=patient_file.name,
            notes="Imported from the UCI Diabetes dataset.",
        )
        db.add(patient)
        db.flush()

        slot_aligned_count = 0
        glucose_count = 0
        duplicate_detector: set[tuple[str, str, int, str]] = set()

        lines = patient_file.read_text(encoding="utf-8", errors="replace").splitlines()
        source_line = 1
        while source_line <= len(lines):
            line = lines[source_line - 1]
            if not line.strip():
                source_line += 1
                continue
            parts = line.split("\t")
            if len(parts) != 4:
                db.add(
                    DataQualityIssue(
                        import_batch_id=import_batch.id,
                        patient_id=patient.id,
                        severity="warning",
                        issue_type="malformed_line",
                        description=f"Line {source_line} in {patient_file.name} does not follow the four-column UCI format.",
                        rule_name="line_shape_validation",
                    )
                )
                source_line += 1
                continue

            raw_date, raw_time, raw_code_str, raw_value = parts
            if raw_code_str == "0" and raw_value == "" and source_line < len(lines) and lines[source_line].startswith("\t"):
                db.add(
                    DataQualityIssue(
                        import_batch_id=import_batch.id,
                        patient_id=patient.id,
                        severity="warning",
                        issue_type="split_placeholder_record",
                        description=(
                            f"Skipped malformed placeholder record spanning lines {source_line}-{source_line + 1} "
                            f"in {patient_file.name}: '{line}' + '{lines[source_line]}'."
                        ),
                        rule_name="placeholder_split_detector",
                    )
                )
                source_line += 2
                continue

            if not raw_date or ":" not in raw_time:
                db.add(
                    DataQualityIssue(
                        import_batch_id=import_batch.id,
                        patient_id=patient.id,
                        severity="warning",
                        issue_type="malformed_timestamp_shape",
                        description=f"Skipped malformed timestamp at line {source_line} in {patient_file.name}: '{line}'.",
                        rule_name="timestamp_shape_validation",
                    )
                )
                source_line += 1
                continue

            try:
                raw_code = int(raw_code_str)
            except ValueError:
                db.add(
                    DataQualityIssue(
                        import_batch_id=import_batch.id,
                        patient_id=patient.id,
                        severity="warning",
                        issue_type="malformed_code",
                        description=f"Skipped malformed code at line {source_line} in {patient_file.name}: '{line}'.",
                        rule_name="code_cast_validation",
                    )
                )
                source_line += 1
                continue
            normalized_payload = _normalize_event(raw_date, raw_time, raw_code, raw_value)
            occurred_at, timestamp_note = _parse_datetime(raw_date, raw_time)
            duplicate_key = (raw_date, raw_time, raw_code, raw_value)
            if duplicate_key in duplicate_detector:
                db.add(
                    DataQualityIssue(
                        import_batch_id=import_batch.id,
                        patient_id=patient.id,
                        severity="warning",
                        issue_type="duplicate_event",
                        description=(
                            f"Duplicated raw event detected at {raw_date} {raw_time} with code {raw_code} and value {raw_value}."
                        ),
                        rule_name="duplicate_detector",
                    )
                )
            duplicate_detector.add(duplicate_key)

            raw_event = RawEvent(
                import_batch_id=import_batch.id,
                patient_id=patient.id,
                source_file=patient_file.name,
                source_line=source_line,
                raw_date=raw_date,
                raw_time=raw_time,
                raw_code=raw_code,
                raw_value=raw_value,
                raw_payload=line,
            )
            quality_note = normalized_payload["quality_note"]
            if timestamp_note:
                quality_note = f"{quality_note} {timestamp_note}".strip() if quality_note else timestamp_note

            normalized_payload = {**normalized_payload, "quality_note": quality_note}

            normalized_event = NormalizedEvent(
                import_batch_id=import_batch.id,
                patient_id=patient.id,
                raw_event=raw_event,
                occurred_at=occurred_at,
                event_date=occurred_at.date(),
                event_time=occurred_at.time(),
                provenance_artifact=str(dataset.zip_path),
                **normalized_payload,
            )
            db.add_all([raw_event, normalized_event])

            raw_count += 1
            normalized_count += 1
            if normalized_payload["matches_slot_time"]:
                slot_aligned_count += 1
            if normalized_payload["is_glucose"]:
                glucose_count += 1
            if normalized_payload["event_type"] == "unknown":
                db.add(
                    DataQualityIssue(
                        import_batch_id=import_batch.id,
                        patient_id=patient.id,
                        severity="error",
                        issue_type="unknown_code",
                        description=f"Unknown code {raw_code} found in the UCI source.",
                        rule_name="uci_codebook",
                    )
                )
            if normalized_payload["quality_note"] and "Numeric value" in str(normalized_payload["quality_note"]):
                db.add(
                    DataQualityIssue(
                        import_batch_id=import_batch.id,
                        patient_id=patient.id,
                        severity="info",
                        issue_type="coerced_numeric_value",
                        description=str(normalized_payload["quality_note"]),
                        rule_name="numeric_coercion",
                    )
                )
            if timestamp_note:
                db.add(
                    DataQualityIssue(
                        import_batch_id=import_batch.id,
                        patient_id=patient.id,
                        severity="warning",
                        issue_type="coerced_timestamp",
                        description=timestamp_note,
                        rule_name="timestamp_coercion",
                    )
                )
            source_line += 1

        if glucose_count and slot_aligned_count / max(glucose_count, 1) >= 0.5:
            db.add(
                DataQualityIssue(
                    import_batch_id=import_batch.id,
                    patient_id=patient.id,
                    severity="info",
                    issue_type="possible_logical_slots",
                    description=(
                        "More than half of the glucose events align with canonical logical slots "
                        "(08:00, 12:00, 18:00, 22:00), suggesting paper-log style timing."
                    ),
                    rule_name="slot_alignment_ratio",
                )
            )

    import_batch.status = "completed"
    import_batch.raw_record_count = raw_count
    import_batch.normalized_record_count = normalized_count
    db.commit()
    db.refresh(import_batch)
    return import_batch, dataset
