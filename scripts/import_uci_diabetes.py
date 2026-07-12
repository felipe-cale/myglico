from __future__ import annotations

from pathlib import Path
import argparse
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal
from app.models.entities import AnalysisRun, ProvenanceArtifact
from app.services.analytics import compute_analytics
from app.services.provenance import write_analytics_provenance, write_import_provenance
from app.services.uci_importer import import_uci_diabetes
from sqlalchemy import desc, select


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the UCI Diabetes dataset into the MyGlico clinical core.")
    parser.add_argument("--force", action="store_true", help="Import even when dataset records already exist.")
    parser.add_argument("--analytics-always", action="store_true", help="Recompute analytics even when a completed run already exists.")
    args = parser.parse_args()

    with SessionLocal() as db:
        import_batch, dataset = import_uci_diabetes(db, skip_if_loaded=not args.force)
        if dataset is not None:
            write_import_provenance(db, import_batch)
            db.commit()

        analytics_run = db.scalars(select(AnalysisRun).order_by(desc(AnalysisRun.started_at))).first()
        should_compute = args.analytics_always or dataset is not None or analytics_run is None
        if should_compute:
            analytics_run = compute_analytics(db, trigger_type="dataset_import")
            write_analytics_provenance(db, analytics_run)
            db.commit()

        artifact_count = db.query(ProvenanceArtifact).count()
        print(
            "Import completed: "
            f"batch={import_batch.id} raw={import_batch.raw_record_count} "
            f"glucose_records={import_batch.normalized_record_count}"
        )
        print(f"Analytics completed: run={analytics_run.id}")
        print(f"Artifacts registered: {artifact_count}")


if __name__ == "__main__":
    main()
