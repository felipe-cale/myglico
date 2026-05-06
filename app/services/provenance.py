from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
import subprocess

from prov.model import ProvDocument
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AnalysisRun, DataSource, GlucoseRecordSource, ImportBatch, ProvenanceArtifact, RawImportRecord


settings = get_settings()


def _git_revision() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[2],
                stderr=subprocess.DEVNULL,
            )
            .decode("utf-8")
            .strip()
        )
    except Exception:
        return "unknown"


def _file_hash(path: str | Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def _base_document() -> ProvDocument:
    document = ProvDocument()
    document.add_namespace("myg", settings.semantic_base_uri)
    document.add_namespace("mygv", settings.semantic_vocab_uri)
    document.add_namespace("ex", "https://myglico.local/execution/")
    return document


def _register_artifact(
    db: Session,
    owner_type: str,
    owner_id: str,
    artifact_type: str,
    artifact_format: str,
    path: str,
) -> ProvenanceArtifact:
    artifact = ProvenanceArtifact(
        owner_type=owner_type,
        owner_id=owner_id,
        artifact_type=artifact_type,
        format=artifact_format,
        path=path,
        content_hash=_file_hash(path),
        hash_algorithm="sha256",
        status="completed",
    )
    db.add(artifact)
    db.flush()
    return artifact


def write_import_provenance(db: Session, import_batch: ImportBatch) -> tuple[str, str]:
    document = _base_document()
    now = datetime.utcnow().isoformat()
    revision = _git_revision()
    data_source = db.get(DataSource, import_batch.data_source_id)
    raw_count = db.scalar(select(func.count(RawImportRecord.id)).where(RawImportRecord.import_batch_id == import_batch.id)) or 0
    glucose_count = (
        db.scalar(select(func.count(GlucoseRecordSource.id)).where(GlucoseRecordSource.import_batch_id == import_batch.id))
        or 0
    )

    importer = document.agent("ex:myglico-importer", {"prov:label": "MyGlico dataset importer"})
    software = document.agent("ex:git-revision", {"prov:label": revision})
    source_attrs = {
        "prov:label": data_source.name if data_source else "unknown",
        "mygv:sourceType": data_source.source_type if data_source else "dataset",
    }
    if data_source and data_source.version:
        source_attrs["mygv:version"] = data_source.version
    source_entity = document.entity(f"ex:data-source-{data_source.id if data_source else 'unknown'}", source_attrs)
    raw_records = document.entity(
        f"ex:raw-import-records-{import_batch.id}",
        {"prov:label": "raw_import_records", "mygv:recordCount": raw_count},
    )
    glucose_records = document.entity(
        f"ex:glucose-records-{import_batch.id}",
        {"prov:label": "glucose_records", "mygv:recordCount": glucose_count},
    )

    import_activity = document.activity(f"ex:dataset-import-{import_batch.id}", now)
    normalize_activity = document.activity(f"ex:dataset-normalization-{import_batch.id}", now)
    document.wasAssociatedWith(import_activity, importer)
    document.wasAssociatedWith(import_activity, software)
    document.wasAssociatedWith(normalize_activity, importer)
    document.used(import_activity, source_entity)
    document.wasGeneratedBy(raw_records, import_activity)
    document.used(normalize_activity, raw_records)
    document.wasGeneratedBy(glucose_records, normalize_activity)
    document.wasDerivedFrom(glucose_records, raw_records)

    json_path = settings.provenance_dir / f"import-{import_batch.id}.json"
    ttl_path = settings.provenance_dir / f"import-{import_batch.id}.ttl"
    document.serialize(json_path, format="json")
    document.serialize(ttl_path, format="rdf", rdf_format="ttl")
    _register_artifact(db, "import_batch", import_batch.id, "provenance", "json", str(json_path))
    _register_artifact(db, "import_batch", import_batch.id, "provenance", "ttl", str(ttl_path))
    return str(json_path), str(ttl_path)


def write_analytics_provenance(db: Session, analytics_run: AnalysisRun) -> tuple[str, str]:
    document = _base_document()
    now = datetime.utcnow().isoformat()
    revision = _git_revision()

    analyst = document.agent("ex:myglico-analytics", {"prov:label": "MyGlico analytics service"})
    software = document.agent("ex:analytics-git-revision", {"prov:label": revision})
    input_entity = document.entity(
        f"ex:glucose-record-set-{analytics_run.id}",
        {"prov:label": "glucose_records", "mygv:fingerprint": analytics_run.input_fingerprint},
    )
    indicator_entity = document.entity(
        f"ex:daily-indicators-{analytics_run.id}",
        {"prov:label": "daily_indicators", "mygv:fingerprint": analytics_run.output_fingerprint},
    )
    config_entity = document.entity(
        f"ex:analysis-config-{analytics_run.id}",
        {"prov:label": analytics_run.algorithm_name, "mygv:algorithmVersion": analytics_run.algorithm_version},
    )

    compute = document.activity(f"ex:compute-daily-indicators-{analytics_run.id}", now)
    anomaly = document.activity(f"ex:detect-anomalies-{analytics_run.id}", now)
    clustering = document.activity(f"ex:cluster-days-{analytics_run.id}", now)
    for activity in [compute, anomaly, clustering]:
        document.wasAssociatedWith(activity, analyst)
        document.wasAssociatedWith(activity, software)
        document.used(activity, input_entity)
        document.used(activity, config_entity)

    document.wasGeneratedBy(indicator_entity, compute)
    document.wasDerivedFrom(indicator_entity, input_entity)

    json_path = settings.provenance_dir / f"analytics-{analytics_run.id}.json"
    ttl_path = settings.provenance_dir / f"analytics-{analytics_run.id}.ttl"
    document.serialize(json_path, format="json")
    document.serialize(ttl_path, format="rdf", rdf_format="ttl")
    _register_artifact(db, "analysis_run", analytics_run.id, "provenance", "json", str(json_path))
    _register_artifact(db, "analysis_run", analytics_run.id, "provenance", "ttl", str(ttl_path))
    return str(json_path), str(ttl_path)
