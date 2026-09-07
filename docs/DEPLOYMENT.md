# Deployment: Render API + PostgreSQL + Vercel frontend

FinAgent remains a deterministic research application. This deployment adds durable managed storage and an optional recent-market monitoring path; it does not add live trading, paper trading, brokerage access, authentication, LLMs, reinforcement learning, or sentiment analysis.

## Architecture

```text
Browser → Vercel (Next.js, frontend/) → Render Web Service (FastAPI) → Render PostgreSQL
                                                 └→ temporary cache/report files (rebuildable)
```

The API reads `DATABASE_URL` at startup. `sqlite:///...` selects SQLite for local development and tests. `postgresql://...` and `postgres://...` select PostgreSQL. The API initializes its versioned schema before serving requests. Dataset metadata and immutable normalized OHLCV rows are stored in the selected database, so production research data does not depend on Render's ephemeral filesystem.

## 1. Create Render PostgreSQL

In the Render Dashboard, select **New > Postgres**.

| Field | Recommended value |
| --- | --- |
| Name | `finagent-postgres` |
| Database | `finagent` |
| User | `finagent` |
| Region | the same region as the API (the supplied Blueprint uses `oregon`) |
| Plan | `0.1c-256mb` or a larger paid plan appropriate for the dataset size |
| Disk | `1 GB` minimum; increase as historical OHLCV datasets grow |

After the database becomes available, open its **Connect** tab. For the Render API, use the **Internal Database URL**, not the external URL. It has the form `postgresql://…` and stays on Render's private network. Never commit it.

The included [render.yaml](../render.yaml) creates this database and wires `DATABASE_URL` automatically through `fromDatabase.connectionString`. If the database already exists, either use the same name or set `DATABASE_URL` manually in the API service's Environment page to its Internal Database URL.

## 2. Deploy the backend on Render

Create a Blueprint from this repository, or create a Render **Web Service** with:

| Render field | Value |
| --- | --- |
| Runtime | `Python` |
| Root Directory | repository root (leave blank) |
| Build Command | `pip install -e ".[api]"` |
| Start Command | `uvicorn finagent.api.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |
| Python version | `3.12.10` (`.python-version`) |
| Region | same as `finagent-postgres` |

Set these API environment variables:

| Name | Value |
| --- | --- |
| `FINAGENT_ENV` | `production` |
| `FRONTEND_ORIGIN` | exact Vercel production origin, for example `https://fin-agent-iota.vercel.app` |
| `DATABASE_URL` | Render PostgreSQL **Internal Database URL** (Blueprint: supplied automatically) |
| `TWELVE_DATA_API_KEY` | Twelve Data API key, set as a Render secret; backend-only, never expose it to Vercel or browser code |
| `LIVE_MARKET_ENABLED` | `false` by default; set `true` only to opt into V1.1 monitoring |
| `LIVE_DEFAULT_SYMBOL` | `AAPL` (or one symbol included in `LIVE_SYMBOLS`) |
| `LIVE_SYMBOLS` | `AAPL` by default; comma-separated configured monitoring symbols |
| `LIVE_INTERVAL` | `1min`, `5min`, or `15min` (default `1min`) |
| `LIVE_BUFFER_SIZE` | `300` (bounded between 50 and 5000 bars) |
| `LIVE_POLL_SECONDS` | `60` by default; do not lower it below the configured 15-second minimum |
| `LIVE_RETENTION` | `500` recent signals/regimes/events per symbol by default |
| `DATA_CACHE_PATH` | `/tmp/finagent-cache` |
| `REPORTS_PATH` | `/tmp/finagent-reports` |
| `LIVE_TRADING_ENABLED` | `false` |

Do **not** set `PORT`; Render supplies it. Do not set `DATABASE_URL` to SQLite in production. The cache and report directories may be ephemeral: cache files are only an optimization, report Markdown is regenerated from persisted research evidence, and canonical dataset rows live in PostgreSQL.

Redeploy and verify:

```text
https://<render-service>/api/health
https://<render-service>/api/system
https://<render-service>/docs
```

`/api/health` must return a response including:

```json
{
  "status": "ok",
  "database_status": "ok",
  "database_backend": "postgresql",
  "database_connectivity": true
}
```

If startup fails, inspect Render logs for `FinAgent database startup failed`; common causes are a malformed URL, an unavailable database, a missing `psycopg` install caused by an incorrect build command, or placing the API and PostgreSQL in different regions.

## 3. Deploy the frontend on Vercel

Import the same repository into Vercel:

| Vercel field | Value |
| --- | --- |
| Framework Preset | `Next.js` |
| Root Directory | `frontend` |
| Build Command | `npm run build` |
| Install Command | `npm install` |
| Output Directory | leave default |
| Node.js | `20.x` or newer |

Add this Production environment variable, then redeploy:

| Name | Value |
| --- | --- |
| `NEXT_PUBLIC_FINAGENT_API_URL` | `https://<render-service>.onrender.com` |

`NEXT_PUBLIC_*` values are compiled into the browser build. A changed backend URL requires a new frontend deployment. No `vercel.json` is needed.

## CORS

FastAPI allows only:

- `FRONTEND_ORIGIN` (one or more exact comma-separated HTTPS/HTTP origins),
- `http://localhost:3000`, and
- `http://127.0.0.1:3000`.

It uses credentials, all methods, and all headers, but never wildcard origins. Set `FRONTEND_ORIGIN=https://fin-agent-iota.vercel.app` exactly—no Markdown brackets, route, trailing path, or `*`. Add a preview domain only if you deliberately want that preview to call the production API.

## First production workflow: real data to experiment

1. Open the deployed **Data** page.
2. In Render, create a Twelve Data API key and set it only as `TWELVE_DATA_API_KEY` on the API service. Redeploy after saving it. It must not be added to Vercel, `NEXT_PUBLIC_*`, a report, or the repository.
3. Open the deployed **Data** page, select `Auto` (or `Twelve Data` to require that source), then fetch `AAPL`, `2022-01-01` through `2023-01-01` at daily interval. Do not set `source_path` in production; that option is for a checked-in local CSV. Auto tries configured Twelve Data first, then Yahoo Finance, Stooq, and a supplied local CSV only after retryable failures.
4. Confirm more than 100 valid rows appear and that the dataset's metadata reports requested provider, actual provider, provider symbol, fetch timestamp, date range, interval, and adjustment mode. This stores provenance, validation output, metadata, and normalized OHLCV rows in PostgreSQL.
5. Run a controlled experiment with the returned `dataset_id` using `POST /api/experiments/run`, for example:

   ```json
   {"config_path":"config/experiments.yaml","dataset_id":"DATA-AUTO-AAPL-1D"}
   ```

   The dataset ID must be the value returned by the fetch request; it is not a guessed ticker string.
6. Open **Experiments** and the experiment detail. Trades, metrics, regime observations, agent decisions, critic/memory records, manifests, validation evidence, candidates, and promotion history are all written to PostgreSQL by their existing controlled workflows.

From a Render shell (or another backend environment with the same secret and `DATABASE_URL`), the provider smoke check is:

```bash
.venv/bin/python scripts/smoke_market_data.py \
  --provider twelve_data --symbol AAPL --start 2022-01-01 --end 2023-01-01
```

It prints requested/actual provider, provider symbol, rows received, date range, dataset ID, and validation status without printing credentials. A Twelve Data account's plan/credits and symbol coverage remain external-provider constraints.

## Live market intelligence on Render

V1.1 live monitoring is separate from historical ingestion and experiments. It makes bounded REST polling requests to Twelve Data because WebSocket availability depends on the account plan. It does not place, simulate, or queue an order.

1. Confirm `TWELVE_DATA_API_KEY` is present only in the Render backend Environment page. Never put it in Vercel, a `NEXT_PUBLIC_*` variable, an API request, or a repository file.
2. Set `LIVE_MARKET_ENABLED=true`, `LIVE_DEFAULT_SYMBOL=AAPL`, `LIVE_SYMBOLS=AAPL`, `LIVE_INTERVAL=1min`, and `LIVE_POLL_SECONDS=60`, then redeploy.
3. Open `https://<render-service>.onrender.com/api/live/status`. It should show `enabled: true`, feed mode `polling`, and one configured symbol. Each symbol reports `provider_health`, `market_state`, `status`, `last_market_bar_timestamp`, and `last_successful_provider_poll`. For AAPL, the XNYS calendar prevents a normal weekend, holiday, pre-market, or after-hours gap from being labelled `DELAYED`; delayed means a stale bar while the regular market is open. Before a valid provider response it may report `CONNECTING` or `OFFLINE`; this is an honest state, not synthetic data.
4. Run this from a Render shell or backend environment that has the same secret:

   ```bash
   .venv/bin/python scripts/smoke_live_market.py --symbol AAPL
   ```

   A success prints the provider, feed mode, symbol, latest timestamp/price, buffered bars, regime, technical state, strategy action, and risk decision. If provider access is unavailable it prints `LIVE PROVIDER UNVERIFIED` and exits non-zero.
5. Open the Vercel `/live` page. It reads only typed `/api/live/*` responses, refreshes at the backend-configured cadence, and shows the live status, a bounded candlestick/volume chart, completed-bar signal markers, regime strip, agent state, and persisted feed events.

The service stores only bounded research evidence in PostgreSQL: live signals, regime observations, and feed events. It does not store an unbounded raw-tick stream. A 429, 5xx, or temporary network failure changes the status to `RATE_LIMITED` or `RECONNECTING` and schedules bounded exponential backoff. The UI shows that condition and has a retry action; it never bypasses the provider's plan limits.

## Local development remains SQLite

```bash
DATABASE_URL=sqlite:///data/finagent.db .venv/bin/python -m uvicorn finagent.api.main:app --host 0.0.0.0 --port 8000
```

Existing YAML `database_path` settings remain valid for CLI/local runs. API-triggered workflows intentionally use the service's `DATABASE_URL`, avoiding accidental writes to a repository-local SQLite file.

SQLite maintenance commands continue to work locally:

```bash
.venv/bin/python scripts/database_maintenance.py health --database data/finagent.db
.venv/bin/python scripts/database_maintenance.py backup --database data/finagent.db --output data/backups/finagent.db
```

For PostgreSQL backups and point-in-time recovery, use Render Postgres operations rather than the SQLite backup utility.

## Post-deploy smoke test

1. Check `/api/health` reports `postgresql`, `ok`, and `true` connectivity.
2. Check `/docs` loads.
3. Fetch a real historical dataset through the Data API/UI, preferably with configured Twelve Data for reliable production use.
4. Run a controlled historical experiment referencing that dataset ID.
5. Refresh the service, then revisit the dataset and experiment to confirm that PostgreSQL—not the temporary cache—retained the data.
6. Open the Vercel UI and confirm browser requests target the Render HTTPS URL with no CORS errors.

Render recommends using a same-region Internal Database URL for service-to-database traffic and documents Blueprint `fromDatabase.connectionString` support. See [Render Postgres connection guidance](https://render.com/docs/postgresql-creating-connecting) and the [Blueprint reference](https://render.com/docs/blueprint-spec).
