# Troubleshooting

## Backend does not start

Run `.venv/bin/python scripts/check_environment.py`. Confirm port 8000 is free, then start `.venv/bin/python -m uvicorn finagent.api.main:app --host 127.0.0.1 --port 8000`. The API health endpoint is `http://127.0.0.1:8000/api/health`.

## Frontend cannot connect

Start FastAPI first. Check `frontend/.env.local`; the default API is `http://127.0.0.1:8000`. Restart `npm run dev` after changing `NEXT_PUBLIC_FINAGENT_API_URL`. The global status strip identifies an unavailable API without exposing a stack trace.

## SQLite is locked or unavailable

Close other local processes using the same database and run `.venv/bin/python scripts/database_maintenance.py health`. FinAgent waits briefly for a lock and uses WAL mode, but SQLite remains a single-machine database. Back up before manual investigation.

## PostgreSQL deployment cannot connect

Confirm `DATABASE_URL` starts with `postgresql://` or `postgres://`, and use the Render **Internal Database URL** from a Web Service in the same region. Redeploy after updating the environment variable. `/api/health` should report `database_backend: "postgresql"` and `database_connectivity: true`; startup logs identify malformed URLs, unavailable databases, and failed schema initialization. The SQLite backup command is deliberately not a PostgreSQL backup mechanism.

## Dataset is missing or invalid

Use `scripts/list_datasets.py` and `scripts/validate_dataset.py`. Review provider, coverage, checksum, adjustment mode, quality score, and issues on the Data page. Re-register a local CSV with `scripts/fetch_data.py`; the registry creates a new immutable revision only when content changes.

## A provider reports an error

Yahoo is a public historical-data dependency and may rate-limit, change availability, or reject symbols. Retry later or use a bundled/local CSV. Provider failures are historical-data errors only; no trading action is attempted.

## npm or Python dependency issue

Use Node 20+ where possible, remove only `frontend/node_modules` if you explicitly intend to reinstall it, then run `npm install`. Recreate `.venv` only when you explicitly choose to replace the virtual environment, then rerun the setup commands. `make check-env` reports which dependency is missing.

## Port already in use

Choose another port explicitly: `API_PORT=8001 .venv/bin/python -m uvicorn finagent.api.main:app --host 127.0.0.1 --port 8001`, then set `NEXT_PUBLIC_FINAGENT_API_URL=http://127.0.0.1:8001` in `frontend/.env.local`.

## V1.0 release export cannot find an experiment

Run `scripts/run_validation.py --config config/final_validation.yaml` first. The exporter needs the emitted experiment identifier and its matching release database. On a clean database this is `EXP-000001`; it is different when prior runs exist. The exporter only reads stored evidence and will not rerun a simulation.

## Release check reports a version or secret-hygiene issue

Run `.venv/bin/python scripts/check_release.py --json` for the exact failure. Keep `.env` files, private-key files, and generated release SQLite databases untracked. Public configuration belongs in the documented `.env.example` files; secrets do not belong in FinAgent.
