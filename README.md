# MyGlico MVP

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

[Português](README.pt-br.md) | **English**

MyGlico is an academic MVP for glycemic monitoring, developed as coursework.
Using the public `UCI Diabetes` dataset as its data source, this repository
demonstrates:

- ingestion and normalization into a relational database;
- an analytics layer for glycemic indicators;
- provenance via `PROV-JSON` and `PROV-TTL`;
- semantic export to RDF with SPARQL queries;
- a web dashboard with a self-contained `React` layer, localized in
  Portuguese (Brazil), English (US), and Spanish, including a localized
  clinical PDF report per patient.

## Architecture

- `FastAPI` for the API and artifact delivery.
- `React + Vite` for the main, self-contained frontend.
- `SQLAlchemy 2.0 + Alembic` for persistence and migrations.
- `MySQL` in Docker Compose, with `SQLite` as a self-contained local fallback.
- Clean clinical core with `patients` and `glucose_records`.
- Origin/traceability layer with `raw_import_records`, `glucose_record_sources`,
  and `data_quality_issues`.
- Transactional database provenance with `provenance_events`.
- `PROV-JSON`, `PROV-TTL`, and RDF artifacts registered as derivatives in
  `provenance_artifacts`.
- `pandas + scikit-learn` for the analytics layer.
- `prov` for provenance.
- `rdflib` for the semantic layer.
- `react-i18next` for the frontend UI and a hand-rolled localized PDF
  generator for the patient clinical report.

## Structure

```text
.
|-- alembic/                          # Migrations that instantiate the MySQL schema
|   `-- versions/                     # Initial schema + UUID clinical core with provenance
|-- app/
|   |-- main.py                       # FastAPI application entry point
|   |-- api/routes.py                 # API routes and the report.pdf endpoint
|   |-- core/                         # Configuration
|   |-- db/                           # SQLAlchemy engine and session
|   |-- models/                       # Relational entities (patients, records, provenance)
|   |-- schemas/                      # Pydantic schemas
|   `-- services/
|       |-- uci_importer.py           # UCI Diabetes importer (raw records + glucose_records)
|       |-- analytics.py              # Materialized metrics, indicators, anomalies, clustering
|       |-- manual_entry.py           # Transactional patient/manual glucose entry with provenance
|       |-- provenance.py             # PROV artifact generation
|       |-- semantic.py               # RDF graph and SPARQL queries
|       `-- clinical_pdf.py           # Localized (pt-BR/en-US/es) patient PDF report generator
|-- artifacts/
|   |-- provenance/                   # Generated PROV-JSON / PROV-TTL
|   `-- semantic/                     # Generated RDF (TTL)
|-- frontend-react/                   # React (Vite) frontend consuming the FastAPI backend
|   |-- public/                       # Static assets served by the frontend
|   `-- src/
|       |-- i18n.js                   # react-i18next setup and language resolution
|       |-- locales/                  # Translation catalogs (pt-BR, en-US, es)
|       |-- components/               # App shell, language switcher, shared UI
|       `-- pages/                    # Overview and patient detail
|-- mappings/
|   `-- myglico-core-r2rml-juma.ttl   # R2RML mapping from MySQL to RDF
|-- ontology/
|   `-- mygv-dpo-extension.owl.ttl    # OWL ontology for the mygv: vocabulary
`-- scripts/
    |-- import_uci_diabetes.py        # Idempotent dataset import + analytics + PROV + RDF
    |-- init_db.py                    # Bring up MySQL, migrate, and import (provenance only)
    `-- bootstrap_db.py               # Local bootstrap wrapper
```

## Running the backend locally

```bash
pip install ".[full]"
alembic upgrade head
python scripts/import_uci_diabetes.py
uvicorn app.main:app --reload
```

The `full` extra adds the analytics/import tooling (numpy, pandas,
scikit-learn, alembic, uvicorn, etc.) to the base API dependencies. A plain
`pip install .` installs only the packages required by the API at request
time — the same set used by the hosted deployment to remain within the
platform's function size limit (see "Deployment on Vercel" below).

Open `http://127.0.0.1:8001/health` to validate the API, or use the React
frontend in development.

## Running with Docker

### Full development environment

```bash
docker compose up --build
```

Environment ports:

- `http://localhost:8000`: React (Vite) frontend with hot reload. The only
  way to serve the web interface.
- `http://localhost:8001`: FastAPI backend, API and artifacts only (no SPA).
- `localhost:3307`: environment MySQL exposed on the host.

In the React environment, calls to `/api`, `/artifacts`, and `/health` are
automatically proxied to the backend.

### Isolated backend

```bash
docker build -t myglico-mvp .
docker run --rm -p 8001:8001 myglico-mvp
```

The backend container:

1. applies migrations;
2. imports the UCI Diabetes dataset via script if the database is empty;
3. generates initial analytics, provenance artifacts, and the RDF graph;
4. starts the FastAPI application.

### Bootstrapping only MySQL + import + provenance

To bring up only MySQL in Docker, apply migrations, and populate an empty
database with just the UCI Diabetes dataset and import provenance:

```bash
python scripts/init_db.py --reset-db
```

This script stops `backend` and `frontend`, brings up only the `db` service,
applies `alembic upgrade head`, and runs the import with
`write_import_provenance`. It does not run analytics, does not generate the
semantic graph, and does not start the web application.

The local import can take a few minutes because it preserves every raw row,
normalizes glucose records, and writes provenance events. The `analysis_outbox`
table can be populated as a queue for future processing, but `analysis_runs`,
`daily_indicators`, and `daily_metrics_current` remain empty in this cut.

To reuse the current database without deleting the volume:

```bash
python scripts/init_db.py
```

## Useful variables

- `MYGLICO_DATABASE_URL`: overrides the database URL.
- `MYGLICO_DEBUG=true`: enables FastAPI debug mode.
- `VITE_API_TARGET`: sets the backend target for the React frontend in
  development.

## Generated artifacts

- `artifacts/provenance/*.json`
- `artifacts/provenance/*.ttl`
- `artifacts/semantic/*.ttl`

## Scope notes

- The main indicator is based on observed measurements, not continuous CGM.
- Times aligned to `08:00`, `12:00`, `18:00`, and `22:00` are marked as
  `slot_aligned` since they may represent logical paper-log times.
- The MVP prioritizes explainability and traceability for coursework purposes.

## Deployment on Vercel

A live demonstration of the MVP is available at
**<https://myglico.vercel.app/>**.

The project is hosted as a single Vercel project that serves the React
frontend and the FastAPI backend under one domain, backed by a managed MySQL
instance. This arrangement keeps the demonstration self-contained: frontend
and API share the same origin (no CORS configuration is required), and the
database is the only external service.

### Deployment architecture

- `vercel.json` defines the build: the frontend is compiled with Vite into
  static output (`frontend-react/dist`), while `/api/*`, `/health`, and
  `/artifacts/*` are rewritten to `api/index.py` — a thin adapter that
  exposes the FastAPI application (`app/main.py`) as a serverless function.
  All remaining paths fall back to `index.html`, preserving client-side
  routing across page reloads.
- `requirements.txt` (repository root) lists the Python dependencies
  installed for the serverless function. It is intentionally narrower than
  the `full` extra in `pyproject.toml`, covering only the packages reachable
  from the application's request-time import graph.
- The Vercel project's Root Directory must be the repository root (not
  `frontend-react`), since the build requires `api/`, `app/`, and
  `requirements.txt` together.

### Dependency footprint of the serverless function

Vercel imposes a 500 MB limit on function bundles. The analytics stack —
`numpy`, `pandas`, and `scikit-learn`, used by `app/services/analytics.py`
for clustering and anomaly detection — pushes a full installation beyond
620 MB. Because the live API never imports that module (it is reached only
by the offline import and analytics scripts), the project's dependencies are
split in two:

- the base install (`pip install .`, mirrored by `requirements.txt`) covers
  only the API: `fastapi`, `sqlalchemy`, `pymysql`, `cryptography`,
  `pydantic-settings`, and `rdflib`;
- the `full` extra (`pip install ".[full]"`) adds the analytics and import
  tooling used locally and in Docker.

This division is sufficient for the MVP demonstration: the dashboard, the
patient detail view, the localized PDF report, and manual glucose entry all
operate normally. A manual entry records the affected day in
`analysis_outbox`/`daily_metrics_current` through
`app/services/analysis_queue.py` (plain SQL, no ML dependency), flagging it
for re-analysis rather than recomputing indicators inline.

As future work, should the platform evolve to recompute analytics in
production — for example, after manual entries or on a schedule — the
analytics pipeline should run as a separate deployment (a scheduled worker
or container executing `compute_analytics` against the same database) rather
than being bundled back into the API function, which would exceed the
platform's size limit.

### Configuration

The deployment requires a single environment variable:

- `MYGLICO_DATABASE_URL`: connection string of the managed MySQL instance,
  e.g. `mysql+pymysql://user:password@host:3306/dbname`. Providers such as
  Aiven document connection strings with an `ssl-mode=REQUIRED` parameter;
  since PyMySQL does not accept it as a connect argument,
  `app/db/session.py` translates it into the equivalent `ssl` option, so the
  provider's connection string can be used verbatim.

### Database preparation

Migrations and the dataset import are one-time data-loading steps, executed
from a local machine against the cloud database rather than from the
serverless function:

```bash
MYGLICO_DATABASE_URL="mysql+pymysql://user:password@host:3306/dbname" alembic upgrade head
MYGLICO_DATABASE_URL="mysql+pymysql://user:password@host:3306/dbname" python scripts/import_uci_diabetes.py
```

### Known limitations

- The function's filesystem is read-only except for `/tmp`, which is cleared
  between cold starts. All API routes operate exclusively on the database,
  so normal usage is unaffected; the `/api/semantic/*` SPARQL endpoints and
  any `/artifacts/*` file not versioned in the repository, however, have no
  data to read in this environment. The frontend does not reference either,
  so the user-facing application is not impacted.
- `rdflib` (required by the semantic/SPARQL routes) is the largest remaining
  dependency, so cold starts are slower than in the local Docker/uvicorn
  setup. New dependencies should be added to `requirements.txt` only when
  they are reachable from `app.main`'s request-time import graph.

## Citation

If you use this repository, cite it using the [`CITATION.cff`](CITATION.cff)
file — GitHub renders a **"Cite this repository"** button from it. A DOI
(Zenodo) will be added once a release is archived.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE). The UCI Diabetes dataset used
as a base has its own terms of use; confirm the official citation and license
at `archive.ics.uci.edu`.
