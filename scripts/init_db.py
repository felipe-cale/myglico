from __future__ import annotations

import argparse
from importlib.util import find_spec
import os
from pathlib import Path
import subprocess
import sys
import time

from sqlalchemy import create_engine, text


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = "mysql+pymysql://myglico:myglico@127.0.0.1:3307/myglico?charset=utf8mb4"
REQUIRED_IMPORT_MODULES = {
    "alembic": "alembic",
    "sqlalchemy": "sqlalchemy",
    "requests": "requests",
    "prov": "prov",
    "unlzw3": "unlzw3",
}


def run_command(command: list[str], *, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=ROOT_DIR, env=env, check=check)


def docker_compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run_command(["docker", "compose", *args], check=check)


def required_modules(database_url: str) -> dict[str, str]:
    modules = dict(REQUIRED_IMPORT_MODULES)
    if database_url.startswith("mysql+pymysql"):
        modules["pymysql"] = "pymysql"
        modules["cryptography"] = "cryptography"
    return modules


def ensure_python_dependencies(database_url: str, install_missing: bool) -> None:
    missing_packages = [package for module, package in required_modules(database_url).items() if find_spec(module) is None]
    if not missing_packages:
        return

    if not install_missing:
        raise RuntimeError(
            "Missing Python dependencies: "
            + ", ".join(missing_packages)
            + ". Install them or rerun without --no-install-deps."
        )

    print("Installing missing Python dependencies: " + ", ".join(missing_packages), flush=True)
    run_command([sys.executable, "-m", "pip", "install", *missing_packages])


def docker_volume_names(*filters: str) -> list[str]:
    command = ["docker", "volume", "ls", "--format", "{{.Name}}"]
    for item in filters:
        command.extend(["--filter", item])
    output = subprocess.check_output(command, cwd=ROOT_DIR, text=True)
    return [line.strip() for line in output.splitlines() if line.strip()]


def compose_project_name() -> str:
    return os.environ.get("COMPOSE_PROJECT_NAME") or ROOT_DIR.name


def mysql_volume_name() -> str:
    project_name = compose_project_name()
    project_candidates = docker_volume_names(
        f"label=com.docker.compose.project={project_name}",
        "label=com.docker.compose.volume=myglico_mysql_data",
    )
    if project_candidates:
        return project_candidates[0]

    label_candidates = docker_volume_names("label=com.docker.compose.volume=myglico_mysql_data")
    if len(label_candidates) == 1:
        return label_candidates[0]

    fallback_name = f"{project_name}_myglico_mysql_data"
    if fallback_name in docker_volume_names():
        return fallback_name
    return fallback_name


def stop_application_services() -> None:
    docker_compose("stop", "frontend", "backend", check=False)


def reset_mysql_volume() -> None:
    print("Resetting MySQL Docker container and data volume...", flush=True)
    stop_application_services()
    docker_compose("rm", "-f", "-s", "db", check=False)
    volume_name = mysql_volume_name()
    run_command(["docker", "volume", "rm", volume_name], check=False)


def start_mysql() -> None:
    print("Starting only the MySQL Docker service...", flush=True)
    stop_application_services()
    docker_compose("up", "-d", "db")


def wait_for_database(database_url: str, timeout_seconds: int) -> None:
    print("Waiting for MySQL readiness...", flush=True)
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            engine = create_engine(database_url, future=True, pool_pre_ping=True)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            engine.dispose()
            print("MySQL is ready.", flush=True)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(2)

    raise RuntimeError(f"MySQL did not become ready within {timeout_seconds}s. Last error: {last_error}")


def run_migrations(database_url: str) -> None:
    print("Applying Alembic migrations...", flush=True)
    env = os.environ.copy()
    env["MYGLICO_DATABASE_URL"] = database_url
    run_command([sys.executable, "-m", "alembic", "upgrade", "head"], env=env)


def import_dataset_with_import_provenance(database_url: str, force: bool) -> None:
    print("Importing UCI Diabetes dataset and writing import provenance. This can take a few minutes...", flush=True)
    os.environ["MYGLICO_DATABASE_URL"] = database_url

    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))

    from app.db.session import SessionLocal
    from app.models.entities import (
        DataQualityIssue,
        GlucoseRecord,
        GlucoseRecordSource,
        Patient,
        ProvenanceArtifact,
        ProvenanceEvent,
        RawImportRecord,
    )
    from app.services.provenance import write_import_provenance
    from app.services.uci_importer import import_uci_diabetes

    with SessionLocal() as db:
        import_batch, dataset = import_uci_diabetes(db, skip_if_loaded=not force)
        json_path, ttl_path = write_import_provenance(db, import_batch)
        db.commit()
        summary = {
            "batch_id": import_batch.id,
            "dataset_imported": dataset is not None,
            "raw_record_count": import_batch.raw_record_count,
            "normalized_record_count": import_batch.normalized_record_count,
            "json_path": json_path,
            "ttl_path": ttl_path,
        }

        counts = {
            "patients": db.query(Patient).count(),
            "raw_import_records": db.query(RawImportRecord).count(),
            "glucose_records": db.query(GlucoseRecord).count(),
            "glucose_record_sources": db.query(GlucoseRecordSource).count(),
            "data_quality_issues": db.query(DataQualityIssue).count(),
            "provenance_events": db.query(ProvenanceEvent).count(),
            "provenance_artifacts": db.query(ProvenanceArtifact).count(),
        }

    print(flush=True)
    print("MyGlico database initialized with dataset import and import provenance.", flush=True)
    print(f"Import batch: {summary['batch_id']}")
    print(f"Dataset imported now: {'yes' if summary['dataset_imported'] else 'no, already loaded'}")
    print(f"Raw records in batch: {summary['raw_record_count']}")
    print(f"Normalized glucose records in batch: {summary['normalized_record_count']}")
    print(f"Import provenance JSON: {summary['json_path']}")
    print(f"Import provenance TTL: {summary['ttl_path']}")
    print("Table counts:")
    for table_name, count in counts.items():
        print(f"  - {table_name}: {count}", flush=True)
    print(flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Start only the MyGlico MySQL Docker service, apply migrations, and populate an empty "
            "database with the UCI Diabetes dataset plus import provenance."
        )
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("MYGLICO_DATABASE_URL", DEFAULT_DATABASE_URL),
        help=f"Database URL used by migrations and import. Default: {DEFAULT_DATABASE_URL}",
    )
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Remove the MySQL Docker container and its data volume before starting db. This deletes Docker database data.",
    )
    parser.add_argument(
        "--force-import",
        action="store_true",
        help="Import even if dataset records already exist. Use carefully because it can duplicate records.",
    )
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Do not start or reset Docker. Use when MySQL is already running.",
    )
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Do not run Alembic migrations before import.",
    )
    parser.add_argument("--timeout", type=int, default=120, help="Seconds to wait for MySQL readiness.")
    parser.add_argument(
        "--no-install-deps",
        action="store_true",
        help="Fail instead of installing missing Python packages required by the import script.",
    )
    args = parser.parse_args()

    ensure_python_dependencies(args.database_url, install_missing=not args.no_install_deps)

    if not args.skip_docker:
        if args.reset_db:
            reset_mysql_volume()
        start_mysql()

    wait_for_database(args.database_url, args.timeout)

    if not args.skip_migrations:
        run_migrations(args.database_url)

    import_dataset_with_import_provenance(args.database_url, force=args.force_import)


if __name__ == "__main__":
    main()
