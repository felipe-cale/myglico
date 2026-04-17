from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, XSD
from rdflib.namespace import PROV
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AnalyticsRun, DailyIndicator, ImportBatch, NormalizedEvent, Patient, RawEvent


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
    "slot_aligned_measurements": """
PREFIX mygv: <https://myglico.local/vocab/>
SELECT ?measurement ?patient ?value
WHERE {
  ?measurement a mygv:GlucoseMeasurement ;
               mygv:belongsToPatient ?patient ;
               mygv:glucoseValueMgDl ?value ;
               mygv:timestampQuality "slot_aligned" .
}
LIMIT 20
""".strip(),
}


def _resource_namespaces() -> tuple[Namespace, Namespace]:
    return Namespace(settings.semantic_base_uri), Namespace(settings.semantic_vocab_uri)


def build_semantic_graph(db: Session, analytics_run: AnalyticsRun) -> str:
    resource, vocab = _resource_namespaces()
    graph = Graph()
    graph.bind("myg", resource)
    graph.bind("mygv", vocab)
    graph.bind("prov", PROV)
    graph.bind("rdfs", RDFS)
    graph.bind("owl", OWL)

    _declare_schema(graph, vocab)

    import_batch = db.get(ImportBatch, analytics_run.import_batch_id)
    patients = db.scalars(select(Patient).order_by(Patient.id)).all()
    events = db.scalars(
        select(NormalizedEvent).where(NormalizedEvent.import_batch_id == analytics_run.import_batch_id).order_by(NormalizedEvent.id)
    ).all()
    raw_events = {raw.id: raw for raw in db.scalars(select(RawEvent).where(RawEvent.import_batch_id == analytics_run.import_batch_id)).all()}
    indicators = db.scalars(
        select(DailyIndicator).where(DailyIndicator.analytics_run_id == analytics_run.id).order_by(DailyIndicator.patient_id, DailyIndicator.indicator_date)
    ).all()

    import_uri = resource[f"import-batch/{import_batch.id}"]
    analytics_uri = resource[f"analytics-run/{analytics_run.id}"]
    graph.add((import_uri, RDF.type, vocab.ImportBatch))
    graph.add((import_uri, RDFS.label, Literal(import_batch.source_name)))
    graph.add((analytics_uri, RDF.type, vocab.AnalyticsRun))
    graph.add((analytics_uri, PROV.wasDerivedFrom, import_uri))

    for patient in patients:
        patient_uri = resource[f"patient/{patient.id}"]
        graph.add((patient_uri, RDF.type, vocab.Patient))
        graph.add((patient_uri, RDFS.label, Literal(patient.display_name)))
        graph.add((patient_uri, vocab.sourcePatientCode, Literal(patient.source_patient_code)))

    for event in events:
        patient_uri = resource[f"patient/{event.patient_id}"]
        raw_event = raw_events.get(event.raw_event_id)
        event_uri = resource[f"event/{event.id}"]
        event_type_uri = getattr(vocab, _class_name_for_event_type(event.event_type))
        graph.add((event_uri, RDF.type, event_type_uri))
        graph.add((event_uri, vocab.belongsToPatient, patient_uri))
        graph.add((event_uri, vocab.occurredAt, Literal(event.occurred_at.isoformat(), datatype=XSD.dateTime)))
        graph.add((event_uri, vocab.timestampQuality, Literal(event.timestamp_quality)))
        if event.glucose_mg_dl is not None:
            graph.add((event_uri, vocab.glucoseValueMgDl, Literal(event.glucose_mg_dl, datatype=XSD.double)))
        if event.insulin_units is not None:
            graph.add((event_uri, vocab.insulinUnits, Literal(event.insulin_units, datatype=XSD.double)))
        if event.context_label:
            graph.add((event_uri, vocab.hasContext, Literal(event.context_label)))
        if raw_event is not None:
            raw_uri = resource[f"raw-event/{raw_event.id}"]
            graph.add((raw_uri, RDF.type, vocab.RawEvent))
            graph.add((raw_uri, RDFS.label, Literal(raw_event.raw_payload)))
            graph.add((event_uri, PROV.wasDerivedFrom, raw_uri))

    for indicator in indicators:
        indicator_uri = resource[f"indicator/{indicator.id}"]
        patient_uri = resource[f"patient/{indicator.patient_id}"]
        graph.add((indicator_uri, RDF.type, vocab.DailyIndicator))
        graph.add((indicator_uri, vocab.belongsToPatient, patient_uri))
        graph.add((indicator_uri, vocab.forDate, Literal(indicator.indicator_date.isoformat(), datatype=XSD.date)))
        if indicator.avg_glucose is not None:
            graph.add((indicator_uri, vocab.avgGlucoseMgDl, Literal(indicator.avg_glucose, datatype=XSD.double)))
        graph.add((indicator_uri, vocab.pctHypo, Literal(indicator.pct_hypo, datatype=XSD.double)))
        graph.add((indicator_uri, vocab.pctInRange, Literal(indicator.pct_in_range, datatype=XSD.double)))
        graph.add((indicator_uri, vocab.pctHyper, Literal(indicator.pct_hyper, datatype=XSD.double)))
        graph.add((indicator_uri, vocab.glucoseEventCount, Literal(indicator.glucose_event_count, datatype=XSD.integer)))
        graph.add((indicator_uri, PROV.wasGeneratedBy, analytics_uri))

    ttl_path = settings.semantic_dir / f"semantic-{analytics_run.id}.ttl"
    graph.serialize(ttl_path, format="ttl")
    return str(ttl_path)


def _declare_schema(graph: Graph, vocab: Namespace) -> None:
    class_names = [
        "Patient",
        "RawEvent",
        "GlucoseMeasurement",
        "InsulinDose",
        "Meal",
        "Exercise",
        "Symptom",
        "SpecialEvent",
        "DailyIndicator",
        "ImportBatch",
        "AnalyticsRun",
    ]
    for class_name in class_names:
        graph.add((vocab[class_name], RDF.type, OWL.Class))
        graph.add((vocab[class_name], RDF.type, RDFS.Class))

    for prop in [
        "belongsToPatient",
        "occurredAt",
        "glucoseValueMgDl",
        "insulinUnits",
        "hasContext",
        "forDate",
        "avgGlucoseMgDl",
        "pctHypo",
        "pctInRange",
        "pctHyper",
        "glucoseEventCount",
        "timestampQuality",
        "sourcePatientCode",
    ]:
        graph.add((vocab[prop], RDF.type, RDF.Property))


def _class_name_for_event_type(event_type: str) -> str:
    return {
        "glucose_measurement": "GlucoseMeasurement",
        "insulin_dose": "InsulinDose",
        "meal": "Meal",
        "exercise": "Exercise",
        "symptom": "Symptom",
        "special_event": "SpecialEvent",
    }.get(event_type, "RawEvent")


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
