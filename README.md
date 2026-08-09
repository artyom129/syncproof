<div align="center">

# SyncProof

### Data migration reconciliation, schema profiling, explainable diffs, and patch-plan generation

**Python · FastAPI · SQLite · Pandas · Excel/CSV/JSON · Fuzzy Matching · Docker**

</div>

SyncProof is a local-first control room for proving that a migration, data import, API synchronization, or system replacement actually moved the right records and values.

Instead of stopping at row counts, it profiles both datasets, applies an explicit field-mapping contract, matches identities, explains field-level differences, detects missing and extra rows, and generates a reviewable patch plan.

## Why it exists

A migration can finish with 100,000 rows on both sides and still be wrong:

```text
Legacy CRM                         New CRM
customer_id                        id
full_name                          name
email                              email_address
plan                               tier
mrr                                monthly_revenue
start_date                         activated_at
             ↓ mapping contract ↓
      exact + fuzzy identity match
             ↓ field rules ↓
      migration acceptance report
```

SyncProof makes those assumptions explicit and leaves evidence for every record.

## Highlights

- CSV, JSON, XLSX and XLSM ingestion
- SHA-256 snapshot fingerprints
- Automatic schema profiling
- Deterministic schema-mapping suggestions
- Null-rate and uniqueness statistics
- Explicit source → target field mappings
- Exact identity matching
- Fuzzy recovery for changed identifiers
- Ambiguity protection when multiple candidates are too close
- Field comparison rules for text, email, numeric values and dates
- Numeric and date tolerances
- `matched`, `fuzzy_matched`, `changed`, `source_only`, `target_only`, and `ambiguous` outcomes
- Field-level explainable diffs
- Quality score for each reconciliation run
- Configurable migration acceptance gates
- Persistent SQLite audit history
- CSV evidence export
- JSON patch-plan generation
- Responsive operations dashboard
- REST API and OpenAPI docs
- Docker / docker-compose
- Automated tests and GitHub Actions
- No external APIs required

## Demo

The repository includes a deliberately imperfect CRM migration.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/seed_demo.py
uvicorn app.main:app --reload
```

Open:

- Dashboard: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/health`

The demo detects clean records, changed fields, a missing target record, an extra legacy target record, and data differences such as plan or date drift.

## Mapping contract

```json
{
  "source_key": "customer_id",
  "target_key": "id",
  "mappings": [
    {"source": "full_name", "target": "name", "rule": "text"},
    {"source": "email", "target": "email_address", "rule": "email"},
    {"source": "mrr", "target": "monthly_revenue", "rule": "numeric_tolerance", "tolerance": 0.01},
    {"source": "start_date", "target": "activated_at", "rule": "date", "tolerance": 0}
  ]
}
```

The contract is versionable, reviewable, and reusable in automated acceptance checks.

## Patch plan

SyncProof does not modify the target system. It produces a safe plan that can be reviewed or consumed by another automation:

```json
{
  "operations": [
    {"operation": "insert", "key": "C-1007", "payload": {}},
    {"operation": "update", "key": "C-1003", "changes": {"tier": "Pro"}},
    {"operation": "review_delete", "key": "C-1010", "payload": {}}
  ]
}
```

## API surface

- `POST /api/datasets` — upload a dataset
- `GET /api/datasets` — list snapshots
- `GET /api/mappings/suggest` — suggest source → target mappings
- `POST /api/runs` — execute a reconciliation
- `GET /api/runs/{id}` — get complete evidence
- `GET /api/runs/{id}/export.csv` — export findings
- `GET /api/runs/{id}/patch-plan.json` — generate corrective plan

## Project structure

```text
app/
  main.py          FastAPI routes and dashboard
  matcher.py       exact/fuzzy matching + field comparison rules
  profiler.py      dataset loading and schema profiling
  repository.py    SQLite persistence and audit history
  services.py      ingestion, reconciliation, exports
  models.py        mapping contracts
  templates/       operations UI
  static/          responsive dashboard styles
scripts/
  seed_demo.py     realistic CRM migration demo
examples/           source, target and mapping contract
docs/               architecture and report semantics
tests/              matcher, profiler and API tests
```

## Tests

```bash
pytest -q
```

## Docker

```bash
docker compose up --build
```

Runtime state is stored under `./data`.

## Good fit for

- CRM / ERP migrations
- spreadsheet-to-database imports
- API synchronization validation
- ETL acceptance testing
- customer or vendor master-data reconciliation
- pre/post migration audits
- repeatable client handoff reports

SyncProof is intentionally local-first: customer datasets do not need to leave the machine just to be compared.
