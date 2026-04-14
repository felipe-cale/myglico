from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess

from prov.model import ProvDocument

from app.core.config import get_settings
from app.models.entities import AnalyticsRun, ImportBatch


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


def _base_document() -> ProvDocument:
    document = ProvDocument()
    document.add_namespace("myg", settings.semantic_base_uri)
    document.add_namespace("mygv", settings.semantic_vocab_uri)
    document.add_namespace("ex", "https://myglico.local/execution/")
    return document


def write_import_provenance(
    import_batch: ImportBatch,
    patient_file_names: list[str],
    data_codes_path: Path,
    domain_description_path: Path,
) -> tuple[str, str]:
    document = _base_document()
    now = datetime.utcnow().isoformat()
    revision = _git_revision()

    importer = document.agent("ex:myglico-importer", {"prov:label": "MyGlico UCI importer"})
    software = document.agent("ex:git-revision", {"prov:label": revision})
    source_zip = document.entity("ex:uci-diabetes-zip", {"prov:label": import_batch.source_url})
    data_codes = document.entity("ex:data-codes", {"prov:label": str(data_codes_path)})
    domain = document.entity("ex:domain-description", {"prov:label": str(domain_description_path)})
    raw_table = document.entity(f"ex:raw-events-{import_batch.id}", {"prov:label": "raw_events"})
    normalized_table = document.entity(f"ex:normalized-events-{import_batch.id}", {"prov:label": "normalized_events"})

    download = document.activity(f"ex:download-{import_batch.id}", now)
    extract = document.activity(f"ex:extract-{import_batch.id}", now)
    parse = document.activity(f"ex:parse-{import_batch.id}", now)
    normalize = document.activity(f"ex:normalize-{import_batch.id}", now)
    load = document.activity(f"ex:load-{import_batch.id}", now)

    for activity in [download, extract, parse, normalize, load]:
        document.wasAssociatedWith(activity, importer)
    document.wasAssociatedWith(load, software)

    document.used(extract, source_zip)
    document.used(parse, data_codes)
    document.used(parse, domain)
    document.used(parse, source_zip)
    document.used(normalize, raw_table)
    document.used(load, normalized_table)
    document.wasGeneratedBy(raw_table, parse)
    document.wasGeneratedBy(normalized_table, normalize)
    document.wasDerivedFrom(normalized_table, raw_table)
    document.wasDerivedFrom(raw_table, source_zip)
    for file_name in patient_file_names[:10]:
        document.entity(f"ex:{file_name}", {"prov:label": file_name})

    json_path = settings.provenance_dir / f"import-{import_batch.id}.json"
    ttl_path = settings.provenance_dir / f"import-{import_batch.id}.ttl"
    document.serialize(json_path, format="json")
    document.serialize(ttl_path, format="rdf", rdf_format="ttl")
    return str(json_path), str(ttl_path)


def write_analytics_provenance(
    analytics_run: AnalyticsRun,
    import_batch: ImportBatch,
    semantic_ttl_path: str,
    indicator_count: int,
) -> tuple[str, str]:
    document = _base_document()
    now = datetime.utcnow().isoformat()
    revision = _git_revision()

    analyst = document.agent("ex:myglico-analytics", {"prov:label": "MyGlico analytics service"})
    software = document.agent("ex:analytics-git-revision", {"prov:label": revision})
    normalized_table = document.entity(
        f"ex:normalized-events-{import_batch.id}",
        {"prov:label": "normalized_events", "mygv:recordCount": import_batch.normalized_record_count},
    )
    indicator_table = document.entity(
        f"ex:daily-indicators-{analytics_run.id}",
        {"prov:label": "daily_indicators", "mygv:recordCount": indicator_count},
    )
    semantic_graph = document.entity(f"ex:semantic-graph-{analytics_run.id}", {"prov:label": semantic_ttl_path})

    compute = document.activity(f"ex:compute-indicators-{analytics_run.id}", now)
    anomaly = document.activity(f"ex:detect-anomalies-{analytics_run.id}", now)
    clustering = document.activity(f"ex:cluster-days-{analytics_run.id}", now)
    export = document.activity(f"ex:semantic-export-{analytics_run.id}", now)

    for activity in [compute, anomaly, clustering, export]:
        document.wasAssociatedWith(activity, analyst)
        document.wasAssociatedWith(activity, software)

    document.used(compute, normalized_table)
    document.used(anomaly, indicator_table)
    document.used(clustering, indicator_table)
    document.used(export, indicator_table)
    document.wasGeneratedBy(indicator_table, compute)
    document.wasGeneratedBy(semantic_graph, export)
    document.wasDerivedFrom(semantic_graph, indicator_table)

    json_path = settings.provenance_dir / f"analytics-{analytics_run.id}.json"
    ttl_path = settings.provenance_dir / f"analytics-{analytics_run.id}.ttl"
    document.serialize(json_path, format="json")
    document.serialize(ttl_path, format="rdf", rdf_format="ttl")
    return str(json_path), str(ttl_path)
