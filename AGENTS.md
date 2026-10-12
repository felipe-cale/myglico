# Repository Guidelines

## Project Structure & Module Organization

MyGlico is a Python 3.12 / FastAPI academic MVP with a self-contained React
(Vite) dashboard. It ingests the public UCI Diabetes dataset into a relational
core, computes glycemic analytics, and records transactional provenance.
`README.md` is the canonical overview; read it before changing behavior.

- `app/main.py` — FastAPI application entry point.
- `app/api/routes.py` — API routes.
- `app/services/uci_importer.py` — download, extraction, raw records, and
  `glucose_records` generation.
- `app/services/analytics.py` — materialized metrics, indicators, anomalies,
  and clustering.
- `app/services/manual_entry.py` — transactional creation of patients and
  manual glucose entries with origin and provenance.
- `app/services/provenance.py` — PROV artifact generation.
- `app/services/clinical_pdf.py` — hand-rolled, localized (pt-BR/en-US/es)
  patient clinical PDF report generator.
- `frontend-react/` — React (Vite) interface consuming the FastAPI backend,
  with its own assets in `public/` and translations in `src/locales/`.
- `scripts/import_uci_diabetes.py` — idempotent dataset import, initial
  analytics, and PROV.
- `scripts/bootstrap_db.py` — local bootstrap wrapper.
- `scripts/render_provenance_png.py` — renders PROV-O `.ttl`/`.json`
  artifacts as PNG diagrams.
- `alembic/versions/` — schema migrations.

## Build, Test, and Development Commands

```bash
pip install ".[full]"                    # base API deps + analytics/import tooling
alembic upgrade head
python scripts/import_uci_diabetes.py
uvicorn app.main:app --reload            # backend on :8001
```

```bash
cd frontend-react
npm install
npm run dev                              # frontend on :8000, proxies /api to :8001
```

```bash
docker compose up --build                # full dev environment: db + backend + frontend
```

The import is idempotent; re-running must not duplicate `glucose_record_sources`
batches.

## Coding Style & Naming Conventions

Backend: 4-space indentation, type hints where useful, concise docstrings only
where the *why* isn't obvious from the code. `snake_case` for functions/variables,
`UPPER_CASE` for constants. Frontend: existing JSX/CSS conventions in
`frontend-react/src`; no comments unless documenting a non-obvious constraint.
Keep IRIs, ontology terms, and PROV identifiers explicit and stable.

Every user-facing string in the frontend and in the clinical PDF report must be
added to all three locales (`pt-BR`, `en-US`, `es`) — see
`frontend-react/src/locales/*.json` and the `STRINGS` dict in
`app/services/clinical_pdf.py`. Do not hardcode Portuguese text in new UI code.

## Testing & Validation Guidelines

After changes to the importer, analytics, or provenance services, re-run the
import script and confirm `analysis_runs`, `daily_indicators`, and
`daily_metrics_current` populate as expected. After frontend changes, start the
dev server and exercise the affected page in a browser — don't rely on a
build-only check. After changes to `clinical_pdf.py`, download the report for
all three `lang` values and confirm the translated strings and locale-aware
date/number formatting.

SQLite (local runs, integration tests, E2E, validators) must always enforce
foreign keys, as MySQL does in deployment: `app/db/session.py` issues
`PRAGMA foreign_keys=ON` on every SQLite connection. Never disable it to make a
test pass; a constraint failure there means the code would fail on MySQL too.
Every raw `sqlite3` connection opened by tests or scripts must also run
`PRAGMA foreign_keys=ON`. When one flush inserts rows that reference each
other, declare the `relationship()` (or flush explicitly) so the unit of work
orders the INSERTs. Changes to persistence or migrations should also be
exercised against MySQL 8 (e.g. `docker compose up db`) before they are
considered done.

## Commit & Pull Request Guidelines

Commits use conventional prefixes such as `feat:`, `fix:`, and `docs:` with a
scoped, imperative summary — for example `feat: add PDF report language param`.

Pull requests should summarize behavior changes, commands run, and artifacts
changed.

### AI-assisted contributions

When a change is co-authored with an AI assistant, attribute it in the commit
message with a trailer so the collaboration is transparent and appears in the
GitHub contributor list:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```

## Reproducibility Notes

Preserve the traceability chain `RawRecord -> GlucoseMeasurement -> Patient`
and its provenance events. Do not commit secrets such as `.env` or database
credentials.
