# Security

## Scope and threat model

FinAgent is a public, read-mostly research viewer deployed as a Vercel
frontend, Render FastAPI service, PostgreSQL database, and server-side market
data providers. The principal risks are credential disclosure, unapproved or
expensive research jobs, malformed input, provider abuse, SQL/path injection,
and reflected internal errors. It is not a brokerage, multi-user platform, or
order-execution service.

Trust boundaries are: the untrusted browser and public API input; the
authenticated administrator mutation API; server-only environment variables;
the configured PostgreSQL service; and external historical-data providers.
Historical simulations and the optional live monitor remain non-executing.

## Public and protected routes

Read endpoints are public. The following routes require the backend-only
`X-FinAgent-Admin-Key` header and are never callable by the public browser UI:

| Route | Purpose |
| --- | --- |
| `POST /api/data/fetch` | ingest/cache a historical dataset |
| `POST /api/data/validate` | change persisted dataset validation state |
| `POST /api/experiments/run` | run and persist an experiment |
| `POST /api/improvements/run` | run bounded candidate evaluation |
| `POST /api/validation/run` | run and persist validation |

Set `FINAGENT_ADMIN_API_KEY` only in the backend environment. The comparison is
constant-time, the value is excluded from settings representations and logs,
and missing/invalid keys receive a structured `401 ADMIN_AUTH_REQUIRED`.
`FINAGENT_DISABLE_ADMIN_AUTH=true` is accepted only with
`FINAGENT_ENV=development`; it is rejected in test and production.

For the narrowly scoped historical experiment and AAPL improvement actions,
Vercel may hold the matching key as the server-only
`FINAGENT_SERVER_ADMIN_API_KEY`. The browser sends only the selected dataset
or explicit AAPL experiment and asset to same-origin Next.js routes; those
routes use the server-only key to attach the backend admin header. They reject
missing secrets, arbitrary configuration paths, incompatible experiment/asset
pairs, and legacy `EXAMPLE` records as AAPL parents. Do not put either key in
`NEXT_PUBLIC_*`, browser requests, rendered HTML, reports, logs, or git.

All other administrative operations remain server-side, for example:

```sh
curl --fail-with-body \
  -H "X-FinAgent-Admin-Key: $FINAGENT_ADMIN_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"provider":"auto","symbol":"AAPL","start_date":"2022-01-01","end_date":"2023-01-01"}' \
  https://YOUR-API.example/api/data/fetch
```

## Rate and resource limits

Authenticated mutation routes are limited to five requests per 300 seconds by
default (`FINAGENT_MUTATION_RATE_LIMIT` and
`FINAGENT_MUTATION_RATE_WINDOW_SECONDS`). A rejected request returns `429
RATE_LIMITED` and `Retry-After`. State is LRU-bounded to 1,024 direct-client
addresses; it cannot grow without bound. This is intentionally **per process**:
it is useful for a small Render deployment but not a replacement for a
distributed edge/WAF rate limiter if the service grows beyond one instance.

The server also bounds date spans to 3,660 days, chart rows, pagination,
report responses (1 MB), candidate generation (5), walk-forward sizes/windows,
and bootstrap samples (10,000). API configuration paths are limited to known
YAML files in `config/`; local CSV ingestion only accepts existing `.csv` files
inside `data/raw/`. Public report reads are separately limited to 10 requests
per client/process per five minutes because a missing report may be safely
materialized from persisted evidence.

## Secrets, providers, data, and logs

`DATABASE_URL`, `TWELVE_DATA_API_KEY`, and `FINAGENT_ADMIN_API_KEY` are read
from server environment variables only. `.env`, certificate/key files,
`secrets/`, caches, local databases, and frontend build output are ignored.
Examples contain placeholders only. Twelve Data is contacted only from the
backend over HTTPS with timeouts and bounded retries; its URL/API key is not
logged, stored in provenance, returned by the API, or included in reports.

Structured logs redact sensitive field names and common URL/query/Bearer token
forms. They never log request bodies or headers. Privileged observability is
limited to `ADMIN_DATA_FETCH`, `ADMIN_DATA_VALIDATE`,
`ADMIN_EXPERIMENT_RUN`, `ADMIN_VALIDATION_RUN`, `ADMIN_IMPROVEMENT_RUN`,
`AUTH_FAILURE`, and `RATE_LIMIT_TRIGGERED` events without credential values.

Persistence uses DB-API bind parameters and transactions. Dynamic ordering and
the one internal live-table name are fixed allowlists, not request data. Health
and system endpoints expose only backend type/connectivity and redact storage
locations. Dataset/report paths are resolved within configured safe roots;
database-backed OHLCV is preferred in production.

## Browser and HTTP protections

CORS permits only the exact configured `FRONTEND_ORIGIN` plus explicitly
listed local development origins; wildcard origins are rejected. The API and
Next.js set `nosniff`, restrictive referrer/frame/permissions policies, CSP,
and production-only HSTS. The CSP preserves required Next/chart runtime
behavior while blocking framing, plugins, unsafe bases, and arbitrary form
destinations.

Reports use `react-markdown` with raw HTML skipped; no component uses
`dangerouslySetInnerHTML`. Only `NEXT_PUBLIC_*` values are browser-visible.
`FINAGENT_API_URL` and `FINAGENT_SERVER_ADMIN_API_KEY` are Vercel server-only
configuration values; the frontend API URL is the sole public configuration
variable. API errors are structured with a request ID; production errors do
not reflect paths, database URLs, provider credentials, SQL, or stack traces.

The live monitor has a server-configured minimum 15-second poll interval,
bounded symbol/buffer/retention settings, and no execution path.
Learning candidates can modify only the pre-existing allowlisted bounded
parameters; they cannot execute code, load modules, or rewrite source. The
promotion gate remains validation-controlled.

## Checks and reporting

Install Python scanner tooling with `pip install -e '.[security]'`, then run
`scripts/security_check.sh` from the repository root. It runs available
`pip-audit`, `bandit`, `npm audit`, and `gitleaks` checks plus backend/frontend
tests. `gitleaks detect --source . --log-opts="--all"` scans reachable git
history when installed. Scanner tooling is not required at application startup.

Report a vulnerability privately to the repository owner. Do not include a
credential, provider key, database URL, or exploit payload in a public issue.
Known limitation: this portfolio deployment has a shared admin key and
per-instance limiting, not individual accounts, distributed throttling, or a
WAF.
