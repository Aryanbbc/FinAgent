# Deployment: Render API + Vercel frontend

FinAgent can be deployed as a public historical-research interface. This deployment does not change any strategy, data, agent, validation, or trading behavior. It remains simulation-only: there is no live trading, paper trading, brokerage connectivity, authentication, LLM, or reinforcement-learning component.

## Architecture

```text
Browser → Vercel (Next.js, frontend/) → Render (FastAPI) → Render persistent disk (SQLite/cache/reports)
```

The frontend receives its API URL through `NEXT_PUBLIC_FINAGENT_API_URL` at build time. The backend accepts browser requests only from explicit CORS origins: local development origins plus `FRONTEND_ORIGIN`. Wildcard CORS is never used.

## 1. Deploy the backend on Render

The repository includes [render.yaml](../render.yaml). Create a **Blueprint** from the repository, or create a Render Web Service using these exact values:

| Render field | Value |
| --- | --- |
| Runtime | `Python` |
| Root Directory | repository root (leave blank) |
| Build Command | `pip install -e ".[api]"` |
| Start Command | `uvicorn finagent.api.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |
| Python version | `3.12.10` (`.python-version` is included) |
| Persistent Disk | mount at `/var/data`, at least `1 GB`, on a paid plan that supports disks |

Set these Render environment variables:

| Name | Value |
| --- | --- |
| `FINAGENT_ENV` | `production` |
| `FRONTEND_ORIGIN` | exact Vercel production origin, e.g. `https://finagent-web.vercel.app` |
| `DATABASE_URL` | `sqlite:////var/data/finagent.db` |
| `DATA_CACHE_PATH` | `/var/data/cache` |
| `REPORTS_PATH` | `/var/data/reports` |
| `LIVE_TRADING_ENABLED` | `false` |

Do **not** add a `PORT` value on Render. Render supplies it; the start command reads `$PORT`. `FRONTEND_ORIGIN` may contain a comma-separated list of exact origins when you deliberately support a preview or custom domain. Do not include paths, trailing routes, or `*`.

After deployment, copy the public backend URL, for example `https://finagent-api.onrender.com`. Verify:

```text
https://finagent-api.onrender.com/api/health
https://finagent-api.onrender.com/docs
```

Render's Blueprint supports a web-service `startCommand`, environment-variable definitions, health paths, and persistent disks. Persistent storage is essential here: without the disk, a redeploy/restart can lose the SQLite database, cache, and report files. [Render Blueprint reference](https://render.com/docs/blueprint-spec), [Render web services](https://render.com/docs/web-services).

## 2. Deploy the frontend on Vercel

Import the same repository into Vercel and use these exact project settings:

| Vercel field | Value |
| --- | --- |
| Framework Preset | `Next.js` |
| Root Directory | `frontend` |
| Build Command | `npm run build` |
| Install Command | `npm install` |
| Output Directory | leave default |
| Node.js | `20.x` or newer |

Add this environment variable for **Production** (and also **Preview** only when that preview origin is explicitly allowed by `FRONTEND_ORIGIN`):

| Name | Value |
| --- | --- |
| `NEXT_PUBLIC_FINAGENT_API_URL` | `https://finagent-api.onrender.com` |

Redeploy after setting it. `NEXT_PUBLIC_*` values are embedded in the browser bundle during the Vercel build, so changing the backend URL requires a new deployment. No `vercel.json` is required for this Next.js app. [Vercel's environment-variable guidance](https://vercel.com/academy/nextjs-foundations/env-and-security).

## Deployment order and CORS

Choose the final Vercel production domain first. Add it as Render's `FRONTEND_ORIGIN`, deploy Render, then use the resulting Render HTTPS URL as Vercel's `NEXT_PUBLIC_FINAGENT_API_URL` and deploy Vercel. This prevents a production build from using any localhost fallback.

Local development remains allowed from `http://localhost:3000` and `http://127.0.0.1:3000`. CORS is a browser-origin policy, not authentication. Because this scoped release intentionally does not add authentication, a public backend is appropriate only for a controlled research/demo deployment; do not treat it as a multi-user or hostile-internet control plane.

## Database persistence and operations

The current repository intentionally uses SQLite APIs and does not support a managed PostgreSQL connection string. Keep `DATABASE_URL`, `DATA_CACHE_PATH`, and `REPORTS_PATH` on the same Render persistent disk.

Use the Render Shell or a controlled maintenance process for backups:

```bash
python scripts/database_maintenance.py health --database /var/data/finagent.db
python scripts/database_maintenance.py backup --database /var/data/finagent.db --output /var/data/backups/finagent-backup.db
```

The backup command refuses to overwrite a target unless `--overwrite` is explicitly supplied. SQLite remains best suited to a small, low-concurrency research deployment; it is not a replacement for a multi-user production database.

## Post-deploy smoke test

1. Open the Vercel URL and confirm the global status reports API/SQLite health.
2. Load Dashboard, Experiments, Agents, Market Regimes, Self-Improvement, Validation, Data, Reports, and System.
3. Open `https://<render-service>/api/health` and `https://<render-service>/docs`.
4. In browser developer tools, confirm API requests target the Render HTTPS URL and have no CORS errors.
5. Run a backup only after verifying the persistent disk mount.
