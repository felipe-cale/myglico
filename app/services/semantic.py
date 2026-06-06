from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, XSD
from rdflib.namespace import PROV
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AnalysisRun, DailyIndicator, GlucoseRecord, GlucoseRecordSource, Patient, ProvenanceArtifact


settings = get_settings()

SAMPLE_QUERIES: dict[str, str] = {
    "all_patients": """
PREFIX mygv: <https://myglico.local/vocab/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?patient ?label
WHERE {
  ?patient a mygv:Patient ;
           rdfs:label ?label .
}
ORDER BY ?label
LIMIT 100
""".strip(),
    "high_risk_days": """
PREFIX mygv: <https://myglico.local/vocab/>
SELECT ?indicator ?date ?pctHypo ?pctHyper
WHERE {
  ?indicator a mygv:DailyIndicator ;
             mygv:forDate ?date ;
             mygv:pctHypo ?pctHypo ;
             mygv:pctHyper ?pctHyper .
  FILTER (?pctHypo > 20 || ?pctHyper > 50)
}
ORDER BY ?date
LIMIT 100
""".strip(),
    "dataset_measurements": """
PREFIX mygv: <https://myglico.local/vocab/>
SELECT ?measurement ?patient ?value
WHERE {
  ?measurement a mygv:GlucoseMeasurement ;
               mygv:belongsToPatient ?patient ;
               mygv:glucoseValueMgDl ?value ;
               mygv:sourceType "dataset" .
}
LIMIT 20
""".strip(),
}


def _resource_namespaces() -> tuple[Namespace, Namespace]:
    return Namespace(settings.semantic_base_uri), Namespace(settings.semantic_vocab_uri)


def _file_hash(path: str | Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def _decimal_literal(value: float) -> Literal:
    return Literal(Decimal(str(value)), datatype=XSD.decimal)


def build_semantic_graph(db: Session, analytics_run: AnalysisRun) -> str:
    resource, vocab = _resource_namespaces()
    graph = Graph()
    graph.bind("myg", resource)
    graph.bind("mygv", vocab)
    graph.bind("prov", PROV)
    graph.bind("rdfs", RDFS)
    graph.bind("owl", OWL)

    _declare_schema(graph, vocab)

    patients = db.scalars(select(Patient).order_by(Patient.name)).all()
    records = db.scalars(select(GlucoseRecord).order_by(GlucoseRecord.measured_at, GlucoseRecord.id)).all()
    sources_by_record: dict[str, list[GlucoseRecordSource]] = {}
    for source in db.scalars(select(GlucoseRecordSource)).all():
        sources_by_record.setdefault(source.glucose_record_id, []).append(source)
    indicators = db.scalars(
        select(DailyIndicator)
        .where(DailyIndicator.analysis_run_id == analytics_run.id)
        .order_by(DailyIndicator.patient_id, DailyIndicator.indicator_date)
    ).all()

    analytics_uri = resource[f"analysis-run/{analytics_run.id}"]
    graph.add((analytics_uri, RDF.type, vocab.AnalysisRun))
    if analytics_run.input_fingerprint:
        graph.add((analytics_uri, vocab.inputFingerprint, Literal(analytics_run.input_fingerprint)))

    for patient in patients:
        patient_uri = resource[f"patient/{patient.id}"]
        graph.add((patient_uri, RDF.type, vocab.Patient))
        graph.add((patient_uri, RDFS.label, Literal(patient.name)))
        if patient.email:
            graph.add((patient_uri, vocab.email, Literal(patient.email)))

    for record in records:
        patient_uri = resource[f"patient/{record.patient_id}"]
        record_uri = resource[f"glucose-record/{record.id}"]
        graph.add((record_uri, RDF.type, vocab.GlucoseMeasurement))
        graph.add((record_uri, vocab.belongsToPatient, patient_uri))
        graph.add((record_uri, vocab.occurredAt, Literal(record.measured_at.isoformat(), datatype=XSD.dateTime)))
        graph.add((record_uri, vocab.glucoseValueMgDl, _decimal_literal(record.glucose_mg_dl)))
        if record.context_label:
            graph.add((record_uri, vocab.hasContext, Literal(record.context_label)))
        for source in sources_by_record.get(record.id, []):
            graph.add((record_uri, vocab.sourceType, Literal(source.source_type)))
            if source.raw_import_record_id:
                raw_uri = resource[f"raw-import-record/{source.raw_import_record_id}"]
                graph.add((record_uri, PROV.wasDerivedFrom, raw_uri))

    for indicator in indicators:
        indicator_uri = resource[f"indicator/{indicator.id}"]
        patient_uri = resource[f"patient/{indicator.patient_id}"]
        graph.add((indicator_uri, RDF.type, vocab.DailyIndicator))
        graph.add((indicator_uri, vocab.belongsToPatient, patient_uri))
        graph.add((indicator_uri, vocab.forDate, Literal(indicator.indicator_date.isoformat(), datatype=XSD.date)))
        if indicator.avg_glucose is not None:
            graph.add((indicator_uri, vocab.avgGlucoseMgDl, _decimal_literal(indicator.avg_glucose)))
        graph.add((indicator_uri, vocab.pctHypo, _decimal_literal(indicator.pct_hypo)))
        graph.add((indicator_uri, vocab.pctInRange, _decimal_literal(indicator.pct_in_range)))
        graph.add((indicator_uri, vocab.pctHyper, _decimal_literal(indicator.pct_hyper)))
        graph.add((indicator_uri, vocab.glucoseEventCount, Literal(indicator.glucose_event_count, datatype=XSD.integer)))
        graph.add((indicator_uri, PROV.wasGeneratedBy, analytics_uri))

    ttl_path = settings.semantic_dir / f"semantic-{analytics_run.id}.ttl"
    graph.serialize(ttl_path, format="ttl")
    db.add(
        ProvenanceArtifact(
            owner_type="analysis_run",
            owner_id=analytics_run.id,
            artifact_type="semantic_graph",
            format="ttl",
            path=str(ttl_path),
            content_hash=_file_hash(ttl_path),
            hash_algorithm="sha256",
            status="completed",
        )
    )
    db.flush()
    return str(ttl_path)


def _declare_schema(graph: Graph, vocab: Namespace) -> None:
    class_names = [
        "Patient",
        "GlucoseMeasurement",
        "DailyIndicator",
        "AnalysisRun",
        "RawImportRecord",
    ]
    for class_name in class_names:
        graph.add((vocab[class_name], RDF.type, OWL.Class))
        graph.add((vocab[class_name], RDF.type, RDFS.Class))

    for prop in [
        "belongsToPatient",
        "occurredAt",
        "glucoseValueMgDl",
        "hasContext",
        "forDate",
        "avgGlucoseMgDl",
        "pctHypo",
        "pctInRange",
        "pctHyper",
        "glucoseEventCount",
        "sourceType",
        "email",
        "inputFingerprint",
    ]:
        graph.add((vocab[prop], RDF.type, RDF.Property))


@lru_cache(maxsize=4)
def _load_graph_cached(ttl_path: str) -> Graph:
    graph = Graph()
    graph.parse(_resolve_graph_path(ttl_path), format="ttl")
    return graph


def load_graph(ttl_path: str | Path) -> Graph:
    return _load_graph_cached(str(ttl_path))


def execute_sparql(ttl_path: str | Path, query: str, limit: int | None = None) -> list[dict[str, str]]:
    graph = load_graph(ttl_path)
    result = graph.query(query)
    rows: list[dict[str, str]] = []
    for index, row in enumerate(result):
        rows.append({str(key): str(value) for key, value in row.asdict().items()})
        if limit is not None and index + 1 >= limit:
            break
    return rows


def _resolve_graph_path(ttl_path: str | Path) -> str:
    candidate = Path(str(ttl_path))
    if candidate.exists():
        return candidate.as_posix()

    fallback_name = str(ttl_path).replace("\\", "/").split("/")[-1]
    fallback = settings.semantic_dir / fallback_name
    if fallback.exists():
        return fallback.as_posix()

    return str(ttl_path)
