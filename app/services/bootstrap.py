from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.entities import AnalyticsRun, ImportBatch
from app.services.analytics import compute_analytics
from app.services.provenance import write_analytics_provenance, write_import_provenance
from app.services.semantic import build_semantic_graph
from app.services.uci_importer import dataset_already_loaded, download_and_extract_dataset, import_uci_diabetes


def bootstrap_application(db: Session) -> tuple[ImportBatch, AnalyticsRun]:
    if dataset_already_loaded(db):
        import_batch = db.scalars(select(ImportBatch).order_by(desc(ImportBatch.imported_at))).first()
        analytics_run = db.scalars(select(AnalyticsRun).order_by(desc(AnalyticsRun.started_at))).first()
        if import_batch is None:
            raise RuntimeError("Database has patient data but no import metadata.")
        if not import_batch.provenance_json_path or not import_batch.provenance_ttl_path:
            dataset = download_and_extract_dataset()
            provenance_json, provenance_ttl = write_import_provenance(
                import_batch,
                [path.name for path in dataset.patient_files],
                dataset.data_codes_path,
                dataset.domain_description_path,
            )
            import_batch.provenance_json_path = provenance_json
            import_batch.provenance_ttl_path = provenance_ttl
            db.commit()
            db.refresh(import_batch)
        if analytics_run is None:
            analytics_run = compute_analytics(db, import_batch)
        if analytics_run is not None and (
            not analytics_run.semantic_ttl_path
            or not analytics_run.provenance_json_path
            or not analytics_run.provenance_ttl_path
        ):
            semantic_ttl_path = build_semantic_graph(db, analytics_run)
            analytics_json, analytics_ttl = write_analytics_provenance(
                analytics_run=analytics_run,
                import_batch=import_batch,
                semantic_ttl_path=semantic_ttl_path,
                indicator_count=len(analytics_run.indicators),
            )
            analytics_run.provenance_json_path = analytics_json
            analytics_run.provenance_ttl_path = analytics_ttl
            analytics_run.semantic_ttl_path = semantic_ttl_path
            db.commit()
            db.refresh(analytics_run)
        return import_batch, analytics_run

    import_batch, dataset = import_uci_diabetes(db)
    provenance_json, provenance_ttl = write_import_provenance(
        import_batch,
        [path.name for path in dataset.patient_files],
        dataset.data_codes_path,
        dataset.domain_description_path,
    )
    import_batch.provenance_json_path = provenance_json
    import_batch.provenance_ttl_path = provenance_ttl
    db.commit()
    db.refresh(import_batch)

    analytics_run = compute_analytics(db, import_batch)
    semantic_ttl_path = build_semantic_graph(db, analytics_run)
    analytics_json, analytics_ttl = write_analytics_provenance(
        analytics_run=analytics_run,
        import_batch=import_batch,
        semantic_ttl_path=semantic_ttl_path,
        indicator_count=len(analytics_run.indicators),
    )
    analytics_run.provenance_json_path = analytics_json
    analytics_run.provenance_ttl_path = analytics_ttl
    analytics_run.semantic_ttl_path = semantic_ttl_path
    db.commit()
    db.refresh(analytics_run)
    return import_batch, analytics_run
