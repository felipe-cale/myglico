from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
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
from app.core.crypto import email_lookup, encrypt_field, generate_short_id, hash_password
from app.models.entities import (
    AnalysisOutbox,
    DataQualityIssue,
    DataSource,
    Doctor,
    GlucoseRecord,
    GlucoseRecordSource,
    ImportBatch,
    Patient,
    PatientDoctorLink,
    PatientSourceLink,
    ProvenanceEvent,
    RawImportRecord,
    UserAccount,
)


settings = get_settings()
UCI_DIABETES_URL = "https://archive.ics.uci.edu/static/public/34/diabetes.zip"
DEMO_PASSWORD = "qwerty"
DEMO_EMAIL_DOMAIN = "demo.myglico.invalid"
DEMO_DOCTOR_EMAIL = f"doctor@{DEMO_EMAIL_DOMAIN}"
LEGACY_DEMO_DOCTOR_EMAIL = "doctor@email.com"
_DEMO_PATIENT_EMAIL = re.compile(
    r"^patient([1-9][0-9]*)@(demo\.myglico\.invalid|email\.com)$", re.IGNORECASE
)
# Canonical time slots observed in the UCI dataset paper-log style records.
# They are used only to flag timestamps that align with typical meal/daypart slots
# during provenance normalization; they do not overwrite the original recorded time.
SLOT_TIMES = {"08:00": "breakfast", "12:00": "lunch", "18:00": "dinner", "22:00": "bedtime"}

# Numeric event mapping transcribed from the UCI Diabetes dataset file
# `Diabetes-Data/Data-Codes`. The `Domain-Description` file gives clinical context,
# but the codebook itself is defined in `Data-Codes` under "The Code field is
# deciphered as follows".
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
    return (db.scalar(select(func.count(GlucoseRecordSource.id)).where(GlucoseRecordSource.source_type == "dataset")) or 0) > 0


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


def _normalize_event(raw_time: str, raw_code: int, raw_value: str) -> dict[str, object]:
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
            "context_label": None,
            "is_glucose": False,
            "timestamp_quality": timestamp_quality,
            "quality_note": "Unknown UCI code encountered during normalization.",
            "transformation_rule": "uci_unknown_code",
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
        "context_label": event_subtype if event_type == "glucose_measurement" else None,
        "is_glucose": bool(metadata.get("is_glucose", False)),
        "timestamp_quality": timestamp_quality,
        "quality_note": " ".join(notes) if notes else None,
        "transformation_rule": f"uci_code_{raw_code}_to_{event_subtype}",
    }


def _content_hash(payload: object) -> str:
    return sha256(repr(payload).encode("utf-8")).hexdigest()


def _get_or_create_data_source(db: Session) -> DataSource:
    source = db.scalar(select(DataSource).where(DataSource.name == "UCI Diabetes", DataSource.version == "UCI-34"))
    if source is None:
        source = DataSource(
            name="UCI Diabetes",
            source_type="dataset",
            uri=UCI_DIABETES_URL,
            version="UCI-34",
        )
        db.add(source)
        db.flush()
    return source


def _get_or_create_patient(
    db: Session,
    data_source: DataSource,
    import_batch: ImportBatch,
    patient_suffix: str,
    source_file: str,
) -> Patient:
    external_code = f"uci-{patient_suffix}"
    link = db.scalar(
        select(PatientSourceLink).where(
            PatientSourceLink.data_source_id == data_source.id,
            PatientSourceLink.external_patient_code == external_code,
        )
    )
    if link is not None:
        link.import_batch_id = import_batch.id
        link.source_file = source_file
        return link.patient

    patient_id = str(uuid4())
    patient = Patient(
        id=patient_id,
        short_id=generate_short_id(
            lambda code: db.scalar(select(Patient.id).where(Patient.short_id == code)) is not None
        ),
        name=f"Paciente UCI {patient_suffix}",
        email=None,
    )
    db.add(patient)
    db.flush()
    db.add(
        PatientSourceLink(
            patient_id=patient.id,
            data_source_id=data_source.id,
            import_batch_id=import_batch.id,
            external_patient_code=external_code,
            source_file=source_file,
        )
    )
    return patient


def _add_quality_issue(
    db: Session,
    import_batch: ImportBatch,
    patient: Patient | None,
    raw_record: RawImportRecord | None,
    severity: str,
    issue_type: str,
    description: str,
    rule_name: str,
) -> None:
    db.add(
        DataQualityIssue(
            source_type="dataset",
            import_batch_id=import_batch.id,
            patient_id=patient.id if patient else None,
            raw_import_record_id=raw_record.id if raw_record else None,
            severity=severity,
            issue_type=issue_type,
            description=description,
            rule_name=rule_name,
        )
    )


def import_uci_diabetes(db: Session, skip_if_loaded: bool = True) -> tuple[ImportBatch, ExtractedDataset | None]:
    if skip_if_loaded and dataset_already_loaded(db):
        latest_batch = db.scalars(select(ImportBatch).order_by(ImportBatch.started_at.desc())).first()
        if latest_batch is None:
            raise RuntimeError("Dataset appears loaded but no import batch was found.")
        return latest_batch, None

    dataset = download_and_extract_dataset()
    data_source = _get_or_create_data_source(db)
    import_batch = ImportBatch(
        data_source_id=data_source.id,
        status="running",
        notes=(
            "MVP import for MyGlico using the UCI Diabetes outpatient monitoring dataset. "
            "The source mixes device timestamps and paper log logical slots."
        ),
    )
    db.add(import_batch)
    db.flush()

    raw_count = 0
    glucose_count = 0
    dirty_days: set[tuple[str, object]] = set()

    for patient_file in dataset.patient_files:
        patient_suffix = patient_file.name.split("-")[-1]
        patient = _get_or_create_patient(db, data_source, import_batch, patient_suffix, patient_file.name)
        slot_aligned_count = 0
        patient_glucose_count = 0
        duplicate_detector: set[tuple[str, str, str, str]] = set()

        lines = patient_file.read_text(encoding="utf-8", errors="replace").splitlines()
        source_line = 1
        while source_line <= len(lines):
            line = lines[source_line - 1]
            if not line.strip():
                source_line += 1
                continue

            parts = line.split("\t")
            raw_record = RawImportRecord(
                import_batch_id=import_batch.id,
                patient_id=patient.id,
                source_file=patient_file.name,
                source_line=source_line,
                raw_payload=line,
                raw_date=parts[0] if len(parts) >= 1 else None,
                raw_time=parts[1] if len(parts) >= 2 else None,
                raw_code=parts[2] if len(parts) >= 3 else None,
                raw_value=parts[3] if len(parts) >= 4 else None,
            )
            db.add(raw_record)
            db.flush()
            raw_count += 1

            if len(parts) != 4:
                _add_quality_issue(
                    db,
                    import_batch,
                    patient,
                    raw_record,
                    "warning",
                    "malformed_line",
                    f"Line {source_line} in {patient_file.name} does not follow the four-column UCI format.",
                    "line_shape_validation",
                )
                source_line += 1
                continue

            raw_date, raw_time, raw_code_str, raw_value = parts
            if raw_code_str == "0" and raw_value == "" and source_line < len(lines) and lines[source_line].startswith("\t"):
                _add_quality_issue(
                    db,
                    import_batch,
                    patient,
                    raw_record,
                    "warning",
                    "split_placeholder_record",
                    f"Skipped malformed placeholder record spanning lines {source_line}-{source_line + 1} in {patient_file.name}.",
                    "placeholder_split_detector",
                )
                source_line += 2
                continue

            if not raw_date or ":" not in raw_time:
                _add_quality_issue(
                    db,
                    import_batch,
                    patient,
                    raw_record,
                    "warning",
                    "malformed_timestamp_shape",
                    f"Skipped malformed timestamp at line {source_line} in {patient_file.name}: '{line}'.",
                    "timestamp_shape_validation",
                )
                source_line += 1
                continue

            try:
                raw_code = int(raw_code_str)
            except ValueError:
                _add_quality_issue(
                    db,
                    import_batch,
                    patient,
                    raw_record,
                    "warning",
                    "malformed_code",
                    f"Skipped malformed code at line {source_line} in {patient_file.name}: '{line}'.",
                    "code_cast_validation",
                )
                source_line += 1
                continue

            normalized_payload = _normalize_event(raw_time, raw_code, raw_value)
            occurred_at, timestamp_note = _parse_datetime(raw_date, raw_time)
            quality_note = str(normalized_payload["quality_note"] or "")
            if timestamp_note:
                quality_note = f"{quality_note} {timestamp_note}".strip()

            duplicate_key = (raw_date, raw_time, raw_code_str, raw_value)
            if duplicate_key in duplicate_detector:
                _add_quality_issue(
                    db,
                    import_batch,
                    patient,
                    raw_record,
                    "warning",
                    "duplicate_event",
                    f"Duplicated raw event detected at {raw_date} {raw_time} with code {raw_code} and value {raw_value}.",
                    "duplicate_detector",
                )
            duplicate_detector.add(duplicate_key)

            if normalized_payload["event_type"] == "unknown":
                _add_quality_issue(
                    db,
                    import_batch,
                    patient,
                    raw_record,
                    "error",
                    "unknown_code",
                    f"Unknown code {raw_code} found in the UCI source.",
                    "uci_codebook",
                )

            if quality_note and "Numeric value" in quality_note:
                _add_quality_issue(
                    db,
                    import_batch,
                    patient,
                    raw_record,
                    "info",
                    "coerced_numeric_value",
                    quality_note,
                    "numeric_coercion",
                )
            if timestamp_note:
                _add_quality_issue(
                    db,
                    import_batch,
                    patient,
                    raw_record,
                    "warning",
                    "coerced_timestamp",
                    timestamp_note,
                    "timestamp_coercion",
                )

            if normalized_payload["is_glucose"] and normalized_payload["glucose_mg_dl"] is not None:
                glucose_record = GlucoseRecord(
                    patient_id=patient.id,
                    measured_at=occurred_at,
                    glucose_mg_dl=float(normalized_payload["glucose_mg_dl"]),
                    context_label=normalized_payload["context_label"],
                    notes=quality_note or None,
                )
                db.add(glucose_record)
                db.flush()
                db.add(
                    GlucoseRecordSource(
                        glucose_record_id=glucose_record.id,
                        source_type="dataset",
                        import_batch_id=import_batch.id,
                        raw_import_record_id=raw_record.id,
                        entered_at=datetime.utcnow(),
                        transformation_rule=str(normalized_payload["transformation_rule"]),
                        metadata_json={
                            "event_type": normalized_payload["event_type"],
                            "event_subtype": normalized_payload["event_subtype"],
                            "numeric_value": normalized_payload["numeric_value"],
                            "timestamp_quality": normalized_payload["timestamp_quality"],
                            "source_file": patient_file.name,
                            "source_line": source_line,
                        },
                    )
                )
                provenance_payload = {
                    "entity": {"glucose_record": glucose_record.id, "raw_import_record": raw_record.id},
                    "activity": "dataset_record_normalization",
                    "used": raw_record.id,
                    "wasGeneratedBy": glucose_record.id,
                    "wasDerivedFrom": raw_record.id,
                }
                db.add(
                    ProvenanceEvent(
                        activity_type="dataset_record_normalization",
                        entity_type="glucose_record",
                        entity_id=glucose_record.id,
                        source_type="raw_import_record",
                        source_id=raw_record.id,
                        occurred_at=datetime.utcnow(),
                        prov_json=provenance_payload,
                        metadata_json={
                            "import_batch_id": import_batch.id,
                            "transformation_rule": normalized_payload["transformation_rule"],
                        },
                        content_hash=_content_hash(provenance_payload),
                    )
                )
                dirty_days.add((patient.id, occurred_at.date()))
                glucose_count += 1
                patient_glucose_count += 1
                if normalized_payload["timestamp_quality"] == "slot_aligned":
                    slot_aligned_count += 1

            source_line += 1

        if patient_glucose_count and slot_aligned_count / max(patient_glucose_count, 1) >= 0.5:
            _add_quality_issue(
                db,
                import_batch,
                patient,
                None,
                "info",
                "possible_logical_slots",
                "More than half of the glucose events align with canonical logical slots (08:00, 12:00, 18:00, 22:00).",
                "slot_alignment_ratio",
            )

    for patient_id, target_date in dirty_days:
        db.add(
            AnalysisOutbox(
                patient_id=patient_id,
                start_date=target_date,
                end_date=target_date,
                trigger_type="dataset_import",
            )
        )

    import_batch.status = "completed"
    import_batch.finished_at = datetime.utcnow()
    import_batch.raw_record_count = raw_count
    import_batch.normalized_record_count = glucose_count
    db.commit()
    db.refresh(import_batch)
    return import_batch, dataset


def provision_demo_accounts(db: Session) -> dict[str, int]:
    """Provision stable demo identities and links for imported UCI patients."""
    data_source = db.scalar(
        select(DataSource).where(DataSource.name == "UCI Diabetes", DataSource.version == "UCI-34")
    )
    if data_source is None:
        return {"patients": 0, "accounts_created": 0, "links_created": 0, "skipped": 0}

    legacy_doctor_email = "doctor-uci@demo.myglico.invalid"
    doctor_account = db.scalar(
        select(UserAccount).where(UserAccount.email_lookup == email_lookup(DEMO_DOCTOR_EMAIL))
    )
    if doctor_account is None:
        doctor_account = db.scalar(
            select(UserAccount).where(UserAccount.email_lookup == email_lookup(legacy_doctor_email))
        )
    if doctor_account is None:
        doctor_account = db.scalar(
            select(UserAccount).where(UserAccount.email_lookup == email_lookup(LEGACY_DEMO_DOCTOR_EMAIL))
        )
    if doctor_account is None:
        doctor_account = UserAccount(
            email=DEMO_DOCTOR_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            account_status="active",
            is_demo=True,
        )
        db.add(doctor_account)
        db.flush()
        doctor_id = str(uuid4())
        doctor = Doctor(
            id=doctor_id,
            short_id=generate_short_id(
                lambda code: db.scalar(select(Doctor.id).where(Doctor.short_id == code)) is not None
            ),
            user_account_id=doctor_account.id,
            name_encrypted=encrypt_field(
                "Médico demonstrativo UCI", table="doctors", column="name", record_id=doctor_id
            ),
            crm_encrypted=None,
            uf_encrypted=None,
            crm_uf_lookup=None,
            is_demo=True,
            declared_verified=False,
        )
        db.add(doctor)
        db.flush()
    else:
        if not doctor_account.is_demo:
            raise RuntimeError("Reserved UCI demo identity collides with a non-demo account")
        doctor = db.scalar(select(Doctor).where(Doctor.user_account_id == doctor_account.id))
        if doctor is None or not doctor.is_demo:
            raise RuntimeError("Reserved UCI demo account has no matching demo doctor")
    source_links = db.scalars(
        select(PatientSourceLink)
        .where(PatientSourceLink.data_source_id == data_source.id)
        .order_by(PatientSourceLink.external_patient_code)
    ).all()
    candidates: list[tuple[Patient, str, UserAccount | None, bool]] = []
    used_indices: set[int] = set()
    created_links = 0
    skipped = 0
    for source_link in source_links:
        patient = source_link.patient
        external_code = source_link.external_patient_code
        legacy_email = f"patient-{external_code}@demo.myglico.invalid"
        account: UserAccount | None = None
        is_legacy_account = False
        if patient.user_account_id is not None:
            account = db.get(UserAccount, patient.user_account_id)
            if account is None or not account.is_demo:
                skipped += 1
                continue
            current_match = _DEMO_PATIENT_EMAIL.fullmatch(account.email.strip())
            is_legacy_account = account.email == legacy_email
            if current_match is None and not is_legacy_account:
                skipped += 1
                continue
        else:
            account = db.scalar(
                select(UserAccount).where(UserAccount.email_lookup == email_lookup(legacy_email))
            )
            if account is not None and not account.is_demo:
                raise RuntimeError("Legacy UCI demo identity collides with a non-demo account")
            is_legacy_account = account is not None
            if account is None:
                # A failed/partial previous transaction is not expected, but this
                # lookup also safely recovers a demo account before linking it.
                candidates.append((patient, external_code, None, False))
                continue
            other_patient = db.scalar(select(Patient).where(Patient.user_account_id == account.id))
            if other_patient is not None and other_patient.id != patient.id:
                raise RuntimeError("Legacy UCI demo account is linked to a different patient")
            patient.user_account_id = account.id
        match = _DEMO_PATIENT_EMAIL.fullmatch(account.email.strip()) if account else None
        if match:
            index = int(match.group(1))
            if index in used_indices:
                raise RuntimeError("Duplicate patient demo email index found")
            used_indices.add(index)
        candidates.append((patient, external_code, account, is_legacy_account))

    next_index = max(used_indices, default=0) + 1
    created_accounts = 0
    for patient, external_code, account, is_legacy_account in candidates:
        if account is None:
            legacy_email = f"patient-{external_code}@demo.myglico.invalid"
            account = db.scalar(
                select(UserAccount).where(UserAccount.email_lookup == email_lookup(legacy_email))
            )
            if account is not None:
                if not account.is_demo:
                    raise RuntimeError("Legacy UCI demo identity collides with a non-demo account")
                other_patient = db.scalar(select(Patient).where(Patient.user_account_id == account.id))
                if other_patient is not None and other_patient.id != patient.id:
                    raise RuntimeError("Legacy UCI demo account is linked to a different patient")
                patient.user_account_id = account.id
                is_legacy_account = True
            else:
                while next_index in used_indices:
                    next_index += 1
                target_email = f"patient{next_index}@{DEMO_EMAIL_DOMAIN}"
                target_owner = db.scalar(
                    select(UserAccount).where(UserAccount.email_lookup == email_lookup(target_email))
                )
                if target_owner is not None:
                    raise RuntimeError("Public demo patient email collides with another account")
                account = UserAccount(
                    email=target_email,
                    password_hash=hash_password(DEMO_PASSWORD),
                    account_status="active",
                    is_demo=True,
                )
                db.add(account)
                db.flush()
                patient.user_account_id = account.id
                created_accounts += 1
                used_indices.add(next_index)
                next_index += 1

        match = _DEMO_PATIENT_EMAIL.fullmatch(account.email.strip())
        if match is None and not is_legacy_account:
            raise RuntimeError("Demo patient account does not have a recognized stable identity")

        if not patient.short_id:
            patient.short_id = generate_short_id(
                lambda code: db.scalar(select(Patient.id).where(Patient.short_id == code)) is not None
            )

        existing_link = db.scalar(
            select(PatientDoctorLink)
            .where(PatientDoctorLink.patient_id == patient.id, PatientDoctorLink.doctor_id == doctor.id)
            .order_by(PatientDoctorLink.requested_at.desc())
        )
        if existing_link is not None:
            # Keep both manual decisions and revoked demo links terminal.
            continue

        link = PatientDoctorLink(
            patient_id=patient.id,
            doctor_id=doctor.id,
            status="ACTIVE",
            decided_at=datetime.utcnow(),
            version=1,
            open_pair_key="open",
        )
        db.add(link)
        db.flush()
        event_payload = {
            "activity": "DemoAssociationProvisioned",
            "association_id": link.id,
            "patient_id": patient.id,
            "doctor_id": doctor.id,
            "external_patient_code": external_code,
        }
        db.add(
            ProvenanceEvent(
                activity_type="DemoAssociationProvisioned",
                entity_type="patient_doctor_link",
                entity_id=link.id,
                source_type="software-agent",
                source_id=data_source.id,
                occurred_at=datetime.utcnow(),
                prov_json=event_payload,
                metadata_json={"import_source": "UCI-34", "actor_kind": "SoftwareImporter"},
                content_hash=_content_hash(event_payload),
            )
        )
        created_links += 1

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "patients": len(source_links),
        "accounts_created": created_accounts,
        "links_created": created_links,
        "skipped": skipped,
    }
