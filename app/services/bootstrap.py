from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.entities import AnalysisRun, ImportBatch
from app.services.analytics import compute_analytics
from app.services.provenance import write_analytics_provenance, write_import_provenance
from app.services.uci_importer import dataset_already_loaded, import_uci_diabetes


def bootstrap_application(db: Session, import_dataset: bool = True) -> tuple[ImportBatch | None, AnalysisRun | None]:
    import_batch: ImportBatch | None = db.scalars(select(ImportBatch).order_by(desc(ImportBatch.started_at))).first()
    analytics_run: AnalysisRun | None = db.scalars(select(AnalysisRun).order_by(desc(AnalysisRun.started_at))).first()

    if import_dataset and not dataset_already_loaded(db):
        import_batch, _ = import_uci_diabetes(db)
        write_import_provenance(db, import_batch)
        db.commit()

    if import_batch is None:
        import_batch = db.scalars(select(ImportBatch).order_by(desc(ImportBatch.started_at))).first()

    if analytics_run is None:
        analytics_run = compute_analytics(db, trigger_type="bootstrap")
        write_analytics_provenance(db, analytics_run)
        db.commit()
    else:
        write_analytics_provenance(db, analytics_run)
        db.commit()

    return import_batch, analytics_run
