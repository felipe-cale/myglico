# MyGlico MVP

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21299080.svg)](https://doi.org/10.5281/zenodo.21299080)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

[Português](README.pt-br.md) | **English**

MyGlico is an academic MVP for glycemic monitoring, developed as coursework.
Using the public `UCI Diabetes` dataset as its data source, this repository
demonstrates:

- ingestion and normalization into a relational database;
- an analytics layer for glycemic indicators;
- provenance via `PROV-JSON` and `PROV-TTL`;
- semantic export to RDF via an R2RML mapping and a custom OWL ontology,
  queryable with any SPARQL engine over the mapped graph;
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
- `PROV-JSON` and `PROV-TTL` artifacts registered as derivatives in
  `provenance_artifacts`.
- `pandas + scikit-learn` for the analytics layer.
- `prov` for provenance.
- R2RML mapping (`mappings/`) plus a custom OWL ontology (`ontology/`) for
  semantic export of the relational core to RDF.
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
|       `-- clinical_pdf.py           # Localized (pt-BR/en-US/es) patient PDF report generator
|-- artifacts/
|   |-- provenance/                   # Generated PROV-JSON / PROV-TTL, plus rendered PROV-O PNGs
|   |-- presentations/                # Slide decks used for the project's checkpoint presentations
|   `-- reports/                      # Final report (PDF)
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
    |-- import_uci_diabetes.py        # Idempotent dataset import + analytics + PROV
    |-- init_db.py                    # Bring up MySQL, migrate, and import (provenance only)
    |-- bootstrap_db.py               # Local bootstrap wrapper
    `-- render_provenance_png.py      # Renders PROV-O .ttl/.json artifacts as PNG diagrams
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

## Authentication, encryption, and database setup

Authenticated API access uses revocable server-side sessions in an
HttpOnly, Secure, SameSite=Lax cookie. A `UserAccount` can be linked to at
most one domain identity: either `Patient` or `Doctor`; registering a second
role with an existing email is rejected. People who need both roles must use
separate accounts and email addresses.

Set `MYGLICO_ENCRYPTION_KEY_V1` and `MYGLICO_LOOKUP_HMAC_KEY` to independent,
32-byte keys encoded as 64 hexadecimal characters before starting the API or
running migrations. The first encrypts protected fields with AES-256-GCM; the
second creates blind lookup indexes. Keep both values in the deployment's
secret store and back them up securely. The key names and rotation requirements
are documented in `app/core/CRYPTO_CONFIGURATION.md`. Never commit real key
values.

For Docker Compose, export both variables in the shell or provide them through
the deployment environment before running `docker compose up --build`.
Migrations preserve existing IDs and encrypt legacy patient identity values.
On SQLite, run `VACUUM` on a stopped/disposable database after the migration to
reclaim pages that may still contain remnants of removed plaintext columns.
For large SQLite backfills, stop all application processes and run `VACUUM`
after the backfill has completed; this reclaims freed pages and is not part of
the migration transaction. Treat every released/applied Alembic revision as
immutable: schema fixes go into a new forward migration, and new migrations
must declare their DDL explicitly instead of deriving it from current ORM
models. The whole chain (0001–0011) now declares frozen, explicit DDL
(`op.create_table`, `op.create_index`, `op.add_column`, `op.drop_table`):
0002 creates the clinical core as it was defined when that revision was
written, 0003–0006 create the account/CSCW tables as originally produced, and
later columns and type changes belong to 0007–0010. Every new revision must
follow the same rule and never call `Model.__table__.create()` or
`Base.metadata.create_all()`. Developers with an older local database must
recreate it from scratch (drop it, run `alembic upgrade head` on an empty
database, then re-run `python scripts/import_uci_diabetes.py`) instead of
relying on its previous schema.

The UCI importer provisions demo accounts only when explicitly requested:

```bash
python scripts/import_uci_diabetes.py --provision-demo-accounts
```

Public demo credentials use `patientN@demo.myglico.invalid` and
`doctor@demo.myglico.invalid`, with the documented demo password `qwerty`;
this scheme is exclusive to public dataset demonstrations. Other clinical
free-text fields (patient names/emails, doctor identity fields, investigation
content, and glucose-record notes) are encrypted at rest. Numeric glucose,
measurement time, context labels, and aggregate metric values remain queryable
for the current analytics algorithm and public UCI analysis workflow.

`glucose_records.measured_at` is stored as a naive UTC timestamp. Manual entries
and UCI diary times are interpreted in the patient's IANA timezone and converted
to UTC before storage; migration 0011 converts historical local wall times once.
Daily analytics, date filters, and displayed event dates convert that instant back
to the patient's timezone (`patients.timezone`); existing and imported patients
default to `America/Sao_Paulo`.

The built-in rate limiter is an in-memory fixed-window guard per API worker.
Deployments with multiple workers or instances should add a shared rate-limit
backend before relying on it as a global abuse-control boundary.

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
3. generates initial analytics and provenance artifacts;
4. starts the FastAPI application.

### Bootstrapping only MySQL + import + provenance

To bring up only MySQL in Docker, apply migrations, and populate an empty
database with just the UCI Diabetes dataset and import provenance:

```bash
python scripts/init_db.py --reset-db
```

This script stops `backend` and `frontend`, brings up only the `db` service,
applies `alembic upgrade head`, and runs the import with
`write_import_provenance`. It does not run analytics and does not start the
web application.

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
- `MYGLICO_NOTIFICATION_DISPATCHER` (`loop` | `off`) and
  `MYGLICO_NOTIFICATION_DISPATCH_INTERVAL_SECONDS` (default `5`): how the
  notification outbox is drained. In-app notifications and unread counters are
  committed together with the event that creates them, so they are visible
  immediately; the outbox only records processing state and retries. With
  `loop` (default on a long-running server) a background task drains it; with
  `off` (default on Vercel, and in the integration tests) use
  `python scripts/notification_outbox.py run [--loop]` or `... stats`. API
  requests never drain the outbox themselves.

## Generated artifacts

- `artifacts/provenance/*.json`
- `artifacts/provenance/*.ttl`
- `artifacts/provenance/*.png` — PROV-O diagrams rendered from the `.ttl`/`.json`
  above via `scripts/render_provenance_png.py`
- `artifacts/presentations/*.pdf` — slide decks used to present the project's
  checkpoints
- `artifacts/reports/MyGlico_RelatorioFinal.pdf` — final report (see
  "Final report" below)

### CSCW provenance export (PROV-O, operator only)

Collaboration events (associations, investigations, messages, prompts,
notifications, authorized detail access) stay in `provenance_events` and are
**not** written to `artifacts/`, which is served publicly at `/artifacts`.
An operator with database access projects them to PROV-O on demand:

```bash
python scripts/export_cscw_provenance.py --output /secure/audit/dir \
  [--patient-id <uuid>] [--since 2026-10-01T00:00:00] [--until 2026-10-08T00:00:00]
```

- `--output` is mandatory; the script refuses `artifacts/`, the provenance
  directory, `frontend-react/public` and `frontend-react/dist`. It writes
  `cscw-provenance[-<patient>].json` (PROV-JSON) and `.ttl` (Turtle).
- No HTTP endpoint exposes it. Who collaborated with whom is clinical
  metadata, so keep the output under the same protection as the database.
- No message content, titles, names, e-mails, CRM, SHORTIDs, revocation
  reasons or filter dates appear as literals. Human agents are pseudonymous
  IRIs (keyed HMAC of the account id under `MYGLICO_LOOKUP_HMAC_KEY`, so they
  are stable across exports and cannot be confirmed without the key) with only
  `mygv:domainRole`.
- Each event becomes a `prov:Activity` (`myg:prov-event/<event id>`).
  Associations and investigations are versioned entities linked by
  `prov:wasRevisionOf`/`prov:specializationOf`. System actions use
  `prov:SoftwareAgent`. Domain terms (`mygv:CollaborationActivity`,
  `mygv:investigatesAtypicalDay`, …) are declared in
  `ontology/mygv-dpo-extension.owl.ttl`. The `activity_type` → PROV-O table
  is in the docstring of `app/services/cscw_provenance.py`.

## Final report

Download the final PDF report:
[MyGlico_RelatorioFinal.pdf](artifacts/reports/MyGlico_RelatorioFinal.pdf)

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
  only the API: `fastapi`, `sqlalchemy`, `pymysql`, `cryptography`, and
  `pydantic-settings`;
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
  between cold starts. All API routes operate exclusively on the database, so
  normal usage is unaffected; any `/artifacts/*` file not versioned in the
  repository, however, has no data to read in this environment. The frontend
  does not reference such files, so the user-facing application is not
  impacted.
- New dependencies should be added to `requirements.txt` only when they are
  reachable from `app.main`'s request-time import graph.
- Serverless functions are frozen between invocations, so the notification
  outbox loop is off here. Notifications and counters are unaffected; pending
  outbox rows can be processed from a local machine with
  `MYGLICO_DATABASE_URL=... python scripts/notification_outbox.py run`.

## Citation

If you use this repository, cite it using the [`CITATION.cff`](CITATION.cff)
file — GitHub renders a **"Cite this repository"** button from it — or via
the archived Zenodo record: **10.5281/zenodo.21299080** (concept DOI, always
resolving to the latest release; version v0.1.0 is `10.5281/zenodo.21299081`).
See the [Zenodo record](https://doi.org/10.5281/zenodo.21299080).

## License

Apache License 2.0 — see [`LICENSE`](LICENSE). The UCI Diabetes dataset used
as a base has its own terms of use; confirm the official citation and license
at `archive.ics.uci.edu`.
