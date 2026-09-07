# Development

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[api,dev,dashboard]"
cd frontend && npm install && cd ..
make check-env
```

`make dev` starts FastAPI and Next.js together; `make api` and `make frontend` start them separately. Streamlit is intentionally separate as a legacy/debug surface.

## Tests and checks

```bash
.venv/bin/python -m pytest -q
cd frontend && npm run check && npm test && npm run build
```

Tests must remain deterministic and must not use a live market-data request. Prefer an isolated temporary SQLite database and mocked provider responses.

## Local operations

`scripts/check_environment.py` validates Python/Node/dependencies, writable directories, and SQLite. `scripts/database_maintenance.py health` runs integrity checks; backup and export commands refuse accidental overwrites. `scripts/seed_demo.py` is idempotent and uses separate `data/demo/` paths.

## V1.0 release evidence

Run the isolated final suite and export its persisted evidence:

```bash
.venv/bin/python scripts/run_validation.py --config config/final_validation.yaml
.venv/bin/python scripts/export_release_artifacts.py --experiment EXP-000001 \
  --database data/release/finagent_v1.db --output reports/v1.0
.venv/bin/python scripts/check_release.py
```

Use the printed experiment identifier when the release database is not fresh. `data/release/` is intentionally ignored because it is generated SQLite state; the portable output under `reports/v1.0/` is versioned.

## Change boundaries

Keep FastAPI routes thin, data/research computation typed and testable, and frontend interaction through `frontend/lib/api.ts`. Preserve V0.1–V0.9 configuration compatibility. Public deployment uses explicit origins and managed PostgreSQL while local development retains SQLite; see [deployment](DEPLOYMENT.md). Do not put credentials, broker behavior, live/paper trading, LLMs, RL, or automated code changes into this repository.
