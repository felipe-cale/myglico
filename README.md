# MyGlico MVP

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

[Português](README.pt-br.md) | **English**

Academic MVP for the MyGlico project, using the public `UCI Diabetes` dataset
as a base for:

- ingestion and normalization into a relational database;
- an analytics layer for glycemic indicators;
- provenance via `PROV-JSON` and `PROV-TTL`;
- semantic export to RDF with SPARQL queries;
- a web dashboard with a self-contained `React` layer, localized in
  Portuguese (Brazil), English (US), and Spanish.

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

`.[full]` pulls in the analytics/import tooling (numpy, pandas, scikit-learn,
alembic, uvicorn, etc.) alongside the base API dependencies. A plain
`pip install .` only installs what `app.main`'s request-time code needs —
that's what the Vercel deployment uses, to stay under its function size
limit (see "Deploying to Vercel" below).

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

## Deploying to Vercel

The repository is set up for a single Vercel project that serves both the
React frontend and the FastAPI backend, sharing one domain (no CORS needed):

- `vercel.json` builds `frontend-react` (Vite) as the static output and
  rewrites `/api/*`, `/health`, and `/artifacts/*` to `api/index.py`, a thin
  wrapper that imports the real FastAPI app (`app/main.py`). Every other path
  falls back to `index.html` so client-side routing works on refresh.
- `requirements.txt` (repo root) lists the backend's Python dependencies for
  Vercel's Python runtime. It's intentionally **narrower** than
  `pyproject.toml`'s `full` extra (see next section) — keep both in sync with
  whatever `app.main`'s request-time import graph actually needs, not with
  the full local/Docker dependency set.
- Set the **Root Directory** of the Vercel project to the repository root
  (not `frontend-react`) — it needs `api/`, `requirements.txt`, and `app/` in
  the same build.

### Why the deployed function's dependencies are trimmed (and what that means going forward)

Vercel Python functions have a **500 MB bundle size limit**. `numpy` +
`pandas` + `scikit-learn` (used by `app/services/analytics.py` for
clustering and anomaly detection) alone pushed a full install past 620 MB.
Since `app.main`'s live request path never imports `analytics.py` — it's
only reachable from `scripts/import_uci_diabetes.py` and the offline
bootstrap — those heavy libraries were split into `pyproject.toml`'s `full`
extra and left out of `requirements.txt` entirely. A plain `pip install .`
(what the Vercel deploy effectively gets) installs only `fastapi`,
`sqlalchemy`, `pymysql`, `cryptography`, `pydantic-settings`, and `rdflib`.

**This is fine for demonstrating the MVP as it stands today**: the dashboard,
patient detail, the PDF report, and creating a manual glucose record all
work — a manual entry still writes to `analysis_outbox`/`daily_metrics_current`
via `app/services/analysis_queue.py` (plain SQL, no ML dependency), it just
marks the day as needing re-analysis rather than recomputing it inline.

**It stops being fine the day you want that re-analysis to actually run in
production** (recomputing clusters/anomalies after a manual entry, or
re-running the importer against fresh data on a schedule). At that point,
don't add `numpy`/`pandas`/`scikit-learn` back to `requirements.txt` — a
single function can't hold both the API and the analytics stack under the
size limit. Instead, run the analytics pipeline as a **separate deployment**:
a small worker (Vercel Cron Job hitting its own lean function, a container
on Railway/Fly/Render, or a scheduled script) that only does
`compute_analytics`, reading the same cloud MySQL database. The API function
stays as-is; the worker owns the heavy dependencies.

Required environment variable:

- `MYGLICO_DATABASE_URL`: connection string for the cloud MySQL instance,
  e.g. `mysql+pymysql://user:password@host:3306/dbname`. Managed MySQL
  providers (Aiven, PlanetScale, etc.) often document connection strings
  with a `ssl-mode=REQUIRED`/`ssl_mode=REQUIRED` query param — PyMySQL
  doesn't accept that as a connect argument, so `app/db/session.py` strips
  it out of the URL and translates it into the `ssl={}` PyMySQL actually
  understands. Paste the provider's connection string as-is.

Before the first deploy (or after schema changes), run migrations and the
dataset import **once, from your machine, against the cloud database** —
these are one-off data-loading steps, not something a serverless request
should trigger:

```bash
MYGLICO_DATABASE_URL="mysql+pymysql://user:password@host:3306/dbname" alembic upgrade head
MYGLICO_DATABASE_URL="mysql+pymysql://user:password@host:3306/dbname" python scripts/import_uci_diabetes.py
```

Known limitations on Vercel:

- The Python function's filesystem is read-only except `/tmp`, which is
  wiped between cold starts. All API routes are DB-only reads (plus one
  DB-only write for manual glucose entries), so this doesn't affect normal
  usage — but the `/api/semantic/*` SPARQL endpoints and any `/artifacts/*`
  file that isn't already committed to the repo won't have anything to read
  in production (the frontend no longer links to them, so nothing breaks in
  the UI; this only affects that unused backend surface).
- `rdflib` (for the semantic/SPARQL routes) is the heaviest thing left in the
  deployed function; cold start is still slower than the local Docker/uvicorn
  setup, but nowhere near what it was with the analytics stack included. If
  you add a new dependency to `app/services/`, check whether it's actually
  reachable from `app.main` before adding it to `requirements.txt` — see the
  section above.

## Citation

If you use this repository, cite it using the [`CITATION.cff`](CITATION.cff)
file — GitHub renders a **"Cite this repository"** button from it. A DOI
(Zenodo) will be added once a release is archived.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE). The UCI Diabetes dataset used
as a base has its own terms of use; confirm the official citation and license
at `archive.ics.uci.edu`.
