# FinAgent

FinAgent is a local, reproducible research workspace for testing deterministic technical strategies on historical OHLCV data. It combines a Python research engine with a FastAPI service and a polished Next.js interface. It is deliberately not a broker, signal service, live-trading product, or financial-advice tool.

**V0.9 — Production Polish** improves the local experience: standardized API errors, operational health information, filters/pagination, quality-focused data views, demo data, safe maintenance tools, and a responsive research UI. The core research architecture remains unchanged.

## What problem it addresses

Historical strategy research is easy to make irreproducible: data can change, costs get omitted, validation can leak future observations, and decisions may be difficult to audit. FinAgent makes the experiment inputs, causal calculations, simulation results, data provenance, and validation evidence explicit and local.

## Features

- Deterministic baseline strategy simulation with configurable transaction costs.
- Causal rule-based market-regime detection and structured Technical → Regime → Strategy → Risk decisions.
- Deterministic Critic Agent and experiment memory; configuration-only, explicit V0.5 candidate evaluation.
- Opt-in V0.6 multi-asset, walk-forward, leakage, sensitivity, bootstrap, ablation, benchmark, and robustness diagnostics.
- Historical-data adapters, normalization, quality checks, deterministic cache paths, immutable SQLite dataset revisions, and collections.
- FastAPI with typed schemas, pagination/filtering, request IDs, structured errors, local health state, and OpenAPI docs.
- Next.js research workspace with dashboard, explorer, data quality, charts, reports, errors/empty/loading states, and responsive navigation.
- Demo seed, environment check, safe SQLite health/backup/export commands, and one-command local startup.
- Deployment-ready FastAPI binding, explicit CORS origins, Render Blueprint, Vercel environment wiring, and persistent-disk documentation.

## Screenshots

The interface is intended to be read like a research notebook rather than a trading terminal.

- **Dashboard:** current experiment metrics, equity/benchmark comparison, drawdown, causal regime timeline, and local health.
- **Experiment explorer:** searchable, sortable, paginated historical experiment archive.
- **Data:** provider, quality score, warnings, checksum, adjustment metadata, coverage, and immutable revisions.
- **Validation:** multi-asset, walk-forward, sensitivity, and robustness evidence.

Run demo mode below to populate representative local views.

## Quick start

Prerequisites: Python 3.11+, Node.js 20+ recommended, and npm.

```bash
git clone <your-repository-url>
cd FinAgent
python3 -m venv .venv
.venv/bin/pip install -e ".[api,dev,dashboard]"
cd frontend && npm install && cd ..
make check-env
```

Start the local application:

```bash
make dev
```

This runs FastAPI at `http://127.0.0.1:8000` and Next.js at `http://localhost:3000`. `Ctrl+C` stops both processes. Streamlit remains a separate legacy/debug interface:

```bash
.venv/bin/streamlit run dashboard/app.py
```

## Demo mode

Demo mode needs no key or network connection. It registers bundled CSV data, creates sample historical experiments, critic/memory records, a validation record, controlled-improvement history, and a Markdown report. Everything is marked as sample data and stored separately under `data/demo/`.

```bash
.venv/bin/python scripts/seed_demo.py
make dev
```

Or seed and start in one command:

```bash
make demo
```

Demo results are deterministic historical simulations—not performance claims and not an invitation to trade.

## Research workflow

Run a normal historical experiment:

```bash
.venv/bin/python scripts/run_experiment.py --config config/experiments.yaml
```

Run explicit V0.6 validation or V0.5 controlled candidate evaluation only when configured:

```bash
.venv/bin/python scripts/run_validation.py --config config/validation.yaml
.venv/bin/python scripts/run_improvement.py --config config/improvement.yaml
```

Fetch/register bundled or public historical daily data:

```bash
.venv/bin/python scripts/fetch_data.py --provider local_csv --symbol EXAMPLE --start 2024-01-01 --end 2024-03-01 --source-path data/raw/example_ohlcv.csv
.venv/bin/python scripts/list_datasets.py
.venv/bin/python scripts/validate_dataset.py --dataset DATA-LOCAL-CSV-EXAMPLE-1D
```

The `yahoo_finance` adapter is historical-data only and can be rate-limited. Tests never call it live.

## API

Start FastAPI on its own when needed:

```bash
.venv/bin/python -m uvicorn finagent.api.main:app --host 127.0.0.1 --port 8000
```

OpenAPI is at `http://127.0.0.1:8000/docs`. The API is local by default and only invokes the existing deterministic workflows. Collection endpoints use bounded `limit`/`offset`; experiments additionally accept `search`, `strategy`, `asset`, `regime`, `status`, date-range, and safe sort parameters. Dataset, candidate, validation, and decision history endpoints are similarly bounded.

Errors use a stable envelope:

```json
{
  "error_code": "DATASET_NOT_FOUND",
  "message": "Dataset not found: DATA-...",
  "details": null,
  "timestamp": "2026-01-01T00:00:00+00:00",
  "request_id": "..."
}
```

## Environment and database maintenance

```bash
.venv/bin/python scripts/check_environment.py
.venv/bin/python scripts/database_maintenance.py health
.venv/bin/python scripts/database_maintenance.py backup --output backups/finagent-$(date +%Y%m%d).db
.venv/bin/python scripts/database_maintenance.py export --output exports/experiment-summary.json
```

Backups and exports refuse to overwrite an existing target unless `backup --overwrite` is explicitly provided. No maintenance command deletes the source database.

## Architecture

```text
historical CSV/provider → normalization + quality → immutable cache/revisions
        ↓
features → causal regimes → optional deterministic agent decision chain → simulator + costs
        ↓
metrics + benchmark → critic + memory → explicit bounded improvement / explicit validation
        ↓
SQLite artifacts + reports → FastAPI service → Next.js workspace / CLI / Streamlit debug view
```

Read [architecture notes](docs/ARCHITECTURE.md) and [research methodology](docs/RESEARCH_METHODOLOGY.md) for boundaries and data flow.

## Project structure

```text
finagent/              core research, data, persistence, API, service modules
config/                defaults, runnable examples, and safe demo configuration
scripts/               CLI runners, data tools, demo seed, health and maintenance tools
frontend/              Next.js local research workspace
dashboard/             legacy/debug Streamlit view
data/                  bundled sample data, local cache, and SQLite database
docs/                  architecture, methodology, development, troubleshooting
tests/                 deterministic Python tests
```

## Version history

| Version | Scope |
| --- | --- |
| V0.1 | Backtesting, strategies, costs, metrics, CSV persistence |
| V0.2 | Causal rule-based market regimes |
| V0.3 | Deterministic Technical, Regime, Strategy, and Risk agents |
| V0.4 | Critic Agent and experiment memory |
| V0.5 | Explicit configuration-bounded candidate evaluation and promotion gate |
| V0.6 | Research validation and robustness diagnostics |
| V0.7 | FastAPI and Next.js local research workspace |
| V0.8 | Historical data providers, quality, cache, revisions, collections |
| V0.9 | Production polish, local operations, demo mode, UX and API consistency |

## Limitations and roadmap

FinAgent works with historical data and deterministic rules. It does not model all market frictions, guarantee future results, provide real-time data, authenticate users, run in the cloud, or execute paper/live trades. Yahoo historical availability is outside this project’s control. SQLite is appropriate for a single local user, not concurrent multi-user deployment.

Future work should remain evidence-driven and preserve reproducibility. It must not silently add LLM trading agents, reinforcement learning, sentiment analysis, brokerage integration, live/paper trading, authentication, or payments without an explicit versioned scope change.

## Verification

```bash
.venv/bin/python -m pytest -q
cd frontend
npm run check
npm test
npm run build
```

See [development notes](docs/DEVELOPMENT.md) and [troubleshooting](docs/TROUBLESHOOTING.md) for local operation.

For public Render/Vercel deployment settings, including required CORS and persistent SQLite-disk configuration, read [deployment instructions](docs/DEPLOYMENT.md).

## Disclaimer

FinAgent is educational/research software. All outcomes are simulated historical results and are not investment advice, trade recommendations, or guarantees of future performance.
