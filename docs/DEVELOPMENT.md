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

## Change boundaries

Keep FastAPI routes thin, data/research computation typed and testable, and frontend interaction through `frontend/lib/api.ts`. Preserve V0.1–V0.8 configuration compatibility. Do not put credentials, broker behavior, live/paper trading, LLMs, RL, or automated code changes into this repository.
