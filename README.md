# FinAgent V0.8

FinAgent is a reproducible quantitative-trading research and simulation platform. V0.8 preserves V0.1–V0.7 and adds a provider-neutral historical market-data, cache, registry, quality, provenance, and collection layer without changing the research engine.

It does **not** provide investment advice, guarantee profitability, use AI agents or reinforcement learning, analyze sentiment, or execute live trades. `LIVE_TRADING_ENABLED=false` is the default safety setting.

## Current stage

V0.8 keeps the local visualization/control boundary and adds immutable historical dataset revisions. It cannot alter code, access broker accounts, or perform live/paper trading.

The research goal is to evaluate whether simple, clearly specified strategies remain robust after costs, across data sets, and against baselines—not to optimize historical profit in isolation. Promotion remains risk-adjusted and held-out; V0.6 can optionally add robustness guardrails, disabled by default.

## Install

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[api,dev,dashboard]'
```

Copy `.env.example` to `.env` only if you need local environment settings; FinAgent does not require any credentials.

## Run an experiment

The bundled example is a deterministic local CSV experiment:

```bash
python scripts/run_experiment.py --config config/experiments.yaml
```

The runner validates `data/raw/example_ohlcv.csv`, generates causal features, detects a rule-based regime at each bar, and—when enabled—runs the Technical, Regime, Strategy, and Risk agents before simulated execution. After the simulation, V0.4 can produce a deterministic critique and memory record. It saves experiments, trades, metrics, regime observations, agent decisions, critiques, and memory to `data/finagent.db`.

Edit `config/experiments.yaml` to select `moving_average`, `momentum`, or `mean_reversion`, change their parameters, choose a local CSV, or adjust transaction costs. Required CSV columns are `timestamp`, `open`, `high`, `low`, `close`, and `volume`; timestamps must be ascending and unique.

Available baseline strategies are moving-average crossover, price momentum, and rolling-z-score mean reversion. They emit `+1` (long), `0` (hold), or `-1` (exit); V0.4 only simulates long positions.

### Regime configuration

The `regime` section of `config/default.yaml` enables V0.2 by default. It controls causal lookback windows and transparent thresholds for `bull`, `bear`, `sideways`, `high_volatility`, `low_volatility`, and `stress`. Each observation returns the primary regime, a 0–1 confidence score, and its rolling return, annualized volatility, moving-average slope, momentum, and drawdown values. Set `regime.enabled: false` to omit regime analysis for a backward-compatible V0.1-style run.

In standalone V0.2-compatible mode, regimes remain observational. When V0.3 agent mode is enabled, RegimeAgent passes the existing detector's typed output into the StrategyAgent and RiskAgent decision flow.

### V0.3 agent decision system

`config/experiments.yaml` enables the V0.3 flow. The agents are deterministic Python rules with typed dataclass inputs and outputs:

- **TechnicalAgent** classifies current causal trend, momentum, volatility, RSI, signal strength, and confidence.
- **RegimeAgent** delegates to the existing V0.2 detector; it does not reimplement regime rules.
- **StrategyAgent** selects one configured baseline strategy and emits `long`, `hold`, or `exit` with machine-readable reason codes.
- **RiskAgent** approves/rejects that proposal or reduces its position size based on confidence, drawdown, volatility, and available cash.

The decision history is saved in SQLite and visible in the dashboard. To retain direct V0.1/V0.2 behavior, set the following in an experiment configuration:

```yaml
agents:
  enabled: false
```

Agent mode requires `regime.enabled: true`. It does not use LLMs or any learning/optimization component.

### V0.4 critique and experiment memory

`config/experiments.yaml` also enables V0.4 critique. After an experiment completes, **CriticAgent** receives the strategy/parameters, performance and benchmark metrics, regime history, agent decision history, trade statistics, and transaction-cost assumptions. It returns typed strengths, weaknesses, failure modes, regime-specific observations, structured recommendations, reason codes, and confidence.

Experiment Memory persists that critique alongside agent version, strategy parameters, regime distribution/performance, metrics, drawdown, turnover, transaction costs, and a decision-history summary. It supports deterministic retrieval such as:

```python
from finagent.database.db import Database
from finagent.database.experiment_repository import ExperimentRepository
from finagent.memory.experiment_memory import ExperimentMemory

memory = ExperimentMemory(ExperimentRepository(Database("data/finagent.db")))
memory.best_performing_strategy_by_regime("sideways")
memory.experiments_with_high_drawdown(0.15)
```

The critic is descriptive during normal experiment execution. V0.5 can read its stored recommendations only inside a separately invoked and opt-in workflow. To preserve V0.1–V0.3-style runs, set `critic.enabled: false`.

### V0.5 controlled improvement loop

V0.5 is off by default (`learning.enabled: false`) and is not called by `run_experiment.py`. First run an experiment with `critic.enabled: true` so that a V0.4 memory record exists. Then explicitly start one bounded research cycle:

```bash
python scripts/run_improvement.py --config config/improvement.yaml
```

The lifecycle is deliberately narrow and auditable:

1. Retrieve one persisted Experiment Memory record and its CriticAgent output.
2. LearningAgent generates deterministic neighbourhood or grid candidates from only the allowlisted values in `learning.search.boundaries`.
3. Each candidate and its unchanged parent run through chronological, non-overlapping out-of-sample test windows. The simulator only receives data through the end of the current test window, so later observations cannot affect that window.
4. PromotionGate compares aggregate held-out Sharpe, drawdown, return, consistency, turnover, transaction costs, and trade count. It records `PROMOTED` or explicit rejection reason codes.
5. SQLite keeps the candidate configuration, every validation window, final decision, and append-only configuration-version history. A promotion creates the next `FinAgent-A0001`-style version; rejection preserves the current version.

The approved candidate surface is limited to moving-average fast/slow windows, momentum and mean-reversion windows/threshold, strategy weights, regime-to-strategy mappings, risk confidence threshold, maximum position size, and volatility limit. Candidates cannot change Python code, data, cost models, agent classes, execution rules, or brokerage settings.

`config/improvement.yaml` demonstrates deterministic neighbourhood search. Set `learning.search.mode: grid` and supply explicit `values` lists for a small configurable grid. The process is reproducible; V0.5 does not implement Bayesian, evolutionary, or random search.

To retain V0.1–V0.4 behavior, leave this default in an experiment or improvement configuration:

```yaml
learning:
  enabled: false
```

### V0.6 research validation and robustness

V0.6 is also disabled by default (`validation.enabled: false`). It does not change `run_experiment.py` or the V0.5 promotion workflow. Run the complete two-dataset example explicitly:

```bash
python scripts/run_validation.py --config config/validation.yaml
```

The supplied validation configuration evaluates the same FinAgent setup across `EXAMPLE` and `EXAMPLE_SECONDARY`, saving one normal `EXP-XXXXXX` experiment plus a linked `VAL-XXXXXX` validation record. Each asset has comparable starting capital, dates, transaction-cost assumptions, and the same strategy/agent configuration. SQLite persists aggregate/per-asset metrics, pass/fail status, window definitions, sensitivity points, ablations, benchmarks, confidence intervals, robustness breakdown, leakage result, and manifest.

#### Walk-forward and leakage methodology

`validation.walk_forward.window_mode` accepts `rolling` or `expanding`. Both require a minimum train/test size; out-of-sample windows are non-overlapping by default. Every saved window includes explicit train/test date boundaries and metrics. The leakage suite rejects unordered or duplicate timestamps, train/test overlap, reused held-out observations (unless explicitly allowed), preprocessing fitted through a test boundary, and feature values that differ from a causal prefix recomputation.

#### Sensitivity, robustness, and intervals

Sensitivity analyses accept only V0.5-approved strategy/risk parameters, with explicit nearby values in `validation.sensitivity.parameters`. Each point reports return, Sharpe, drawdown, turnover, costs, and a local stability score relative to the parameter's median Sharpe.

The 0–1 robustness score is transparent and decomposed into weighted asset consistency, walk-forward consistency, sensitivity stability, drawdown control, turnover stability, and benchmark consistency. Its weights and drawdown reference limit live in `validation.robustness`; it is a heuristic diagnostic, not an opaque model or proof of generalization.

Bootstrap confidence intervals are labelled **estimated**. They resample realized historical equity returns using the configured seed, sample count, and confidence level. They describe only the observed sample and do not account for serial dependence, regime shifts, multiple testing, or model-selection uncertainty.

#### Ablations, benchmarks, manifest, and report export

The ablation table runs controlled variants: baseline strategy; + regime; + agents; + critic/memory; + self-improvement. Critic/memory and learning are post-experiment components, so their ablation rows do not imply intrabar decision effects. The benchmark suite uses the same raw data, date range, capital, and transaction costs for buy-and-hold, moving average, momentum, and mean reversion.

Every standard experiment stores a reproducibility manifest with its config snapshot, dataset SHA-256 identifiers, asset/date information, enabled modules, seeds, costs, code version when Git is available, evaluation mode, and walk-forward settings. Export a structured Markdown report without rerunning research:

```bash
python scripts/export_report.py --experiment EXP-000001
```

By default the report is written to `reports/EXP-000001_research_report.md`; use `--output` or `--database` to override its location or SQLite file.

Optional V0.6 promotion constraints are accepted in `learning.promotion_gate`: `minimum_robustness_score`, `minimum_assets`, `require_stable_sensitivity`, `require_no_leakage`, and `require_acceptable_confidence_interval`. All are disabled unless explicitly set, so V0.5 behavior is unchanged.

## Dashboard

After at least one experiment has been saved, run:

```bash
streamlit run dashboard/app.py
```

This Streamlit screen is retained as the **Legacy / Debug Dashboard**. It shows the latest experiment summary, key metrics, latest regime and agent decision, V0.4 Experiment Critique, regime/agent histories, evolution, and V0.6 research-validation records. The V0.7 Next.js workspace below is the primary interface.

## V0.7 local API and research workspace

Start the typed FastAPI service from the repository root:

```bash
uvicorn finagent.api.main:app --host 127.0.0.1 --port 8000
```

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`. The API is local-only by default and allows CORS only from `http://localhost:3000` and `http://127.0.0.1:3000`—never `*`. Environment defaults are documented in `.env.example`:

```dotenv
DATABASE_URL=sqlite:///data/finagent.db
API_HOST=127.0.0.1
API_PORT=8000
```

The read endpoints expose health, experiments, trades, causal regimes, structured decision records, critiques, configuration versions, controlled-improvement evaluations, V0.6 validation, reports, safe configuration, and system metadata. Collection routes provide bounded `limit`/`offset` pagination; experiment lists also support ID/strategy/asset/date filters. Missing artifacts return a structured `404`; malformed requests receive FastAPI `422` validation responses.

The three POST endpoints—`/api/experiments/run`, `/api/improvements/run`, and `/api/validation/run`—require a `config_path` referencing an existing YAML file under `config/`. They invoke only the existing deterministic local workflows and return metadata labelled `local_historical_simulation`. They are not asynchronous execution infrastructure and never execute a broker/paper-trading action.

Start the frontend in a second terminal:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. Set `NEXT_PUBLIC_FINAGENT_API_URL` in `frontend/.env.local` when the API is not at `http://127.0.0.1:8000`. The App Router workspace includes Dashboard, Experiments, Agents, Market Regimes, Self-Improvement, Validation, Reports, and System pages. It uses a centralized typed API client; it does not access SQLite from the browser. The pages disclose only persisted structured inputs, outputs, decisions, reason codes, and metrics—not hidden chain-of-thought.

## V0.8 data and market intelligence layer

FinAgent now has a provider-neutral `MarketDataProvider` contract. The shipped providers are:

- `local_csv`: the original strict, backward-compatible local CSV workflow.
- `yahoo_finance`: a small public historical daily OHLCV adapter. It is isolated behind the provider contract, uses no brokerage functionality or credentials, and is tested with mocked responses.

All provider output is normalized to UTC `timestamp`, `open`, `high`, `low`, `close`, and `volume`. The validation pipeline reports required-column, chronology, duplicate, NaN, non-positive-price, negative-volume, OHLC-bound, suspicious-gap, and timezone findings. Its transparent quality score averages completeness, duplicate rate, chronological consistency, OHLC validity, gap severity, and timezone consistency.

The default missing-data policy is `reject`. `drop`, explicit past-only `forward_fill`, and `warn_only` are available for data curation; none can backfill future values. Dataset metadata records provider, symbol, asset metadata where available, adjustment mode, checksum, quality/validation output, dates, row count, cache path, and refresh timestamps.

Fetched data is cached under deterministic paths in `data/cache/`. The SQLite registry creates a stable dataset ID and immutable `V001`-style content revisions. A force refresh that changes the checksum creates a new revision; an unchanged refresh updates only its refresh/validation metadata. Existing experiment manifests now include dataset ID, revision, provider, symbol, fetch date, checksum, range, and adjustment mode when `experiment.dataset_id` is used.

Register a dataset without any network dependency:

```bash
python scripts/fetch_data.py --provider local_csv --symbol EXAMPLE --start 2024-01-01 --end 2024-03-01 \
  --source-path data/raw/example_ohlcv.csv
python scripts/list_datasets.py
python scripts/validate_dataset.py --dataset DATA-LOCAL-CSV-EXAMPLE-1D
```

For public historical daily data, use the same command with `--provider yahoo_finance --symbol AAPL`. Provider availability, rate limits, empty results, invalid symbols, and malformed responses return structured errors; tests do not call the internet.

Use a registered revision in an experiment while preserving all path-based configuration:

```yaml
experiment:
  asset: EXAMPLE
  dataset_id: DATA-LOCAL-CSV-EXAMPLE-1D
  starting_capital: 100000.0
```

Named collections lock members to their current revisions for multi-asset V0.6 validation:

```bash
python scripts/create_collection.py --name US_TECH_SAMPLE --datasets DATA-YAHOO-FINANCE-AAPL-1D DATA-YAHOO-FINANCE-MSFT-1D
```

```yaml
validation:
  enabled: true
  dataset_collection_id: COLL-US-TECH-SAMPLE
```

The local API adds `GET /api/data/providers`, `GET /api/data/datasets`, `GET /api/data/datasets/{dataset_id}`, `POST /api/data/fetch`, `POST /api/data/validate`, and `GET /api/data/collections`. The **Data** UI page lists datasets/collections and offers a local fetch form; its detail view renders metadata, quality components/issues, normalized sample rows, close/volume chart, and version history.

## Test

```bash
python -m pytest -q
```

The Python suite covers invalid data, causal technical/regime behavior, all three strategies, all six regimes, V0.3 agents/risk gating, deterministic critique findings, memory persistence/retrieval, configuration compatibility, accounting/costs, metrics, SQLite persistence, V0.5 allowlist constraints, reproducible candidates, promotion/rejection, immutable versions, multi-asset execution/aggregation, V0.6 validation, V0.7 API behavior, and V0.8 mocked-provider, normalization, quality, cache, checksum revision, collection, dataset reference, provenance, and data API behavior.

Frontend checks are deliberately lightweight:

```bash
cd frontend
npm run check
npm test
npm run build
```

## Architecture

```text
CSV OHLCV → validation → feature pipeline → TechnicalAgent → StrategyAgent → RiskAgent → simulator
                    │                         │                │                │
                    └→ rule-based detector → RegimeAgent ──────┘                │
                                                            portfolio + transaction costs
                                                                        ↓
                                                   metrics + buy-and-hold benchmark
                                                                        ↓
                              CriticAgent → Experiment Memory
                                                                        ↓
        explicit user invocation → LearningAgent → bounded CandidateGenerator
                                                                        ↓
                               chronological Walk-Forward Evaluator → PromotionGate
                                                                        ↓
                       immutable Configuration Versions + candidate/validation SQLite history
                                                                        ↓
        explicit V0.6 validation → multi-asset / leakage / sensitivity / bootstrap / ablation / benchmarks
                                                                        ↓
                              robustness score + reproducibility manifest + Markdown report
                                                                        ↓
               provider adapters → normalization/quality → deterministic cache → dataset registry/revisions
                                                                        ↓
                            dataset provenance + V0.6 collections → FastAPI service layer → Next.js workspace
                                                                        ↓
                                                 CLI and Legacy / Debug Streamlit dashboard
```

Key source directories:

- `finagent/data`: provider interface, CSV loader, strict OHLCV validator.
- `finagent/features`: configurable, look-ahead-safe technical indicators.
- `finagent/strategies`: moving-average, momentum, and mean-reversion baselines.
- `finagent/backtesting`: cost model, execution sizing, portfolio accounting, and causal engine.
- `finagent/evaluation`: performance metrics and buy-and-hold benchmark.
- `finagent/regime`: causal regime features, typed outputs, and rule-based detector.
- `finagent/agents`: reusable base contract plus technical, regime, strategy, risk, and decision-system agents.
- `finagent/critique`: deterministic CriticAgent and typed critique schemas.
- `finagent/memory`: typed experiment memory records and retrieval helpers.
- `finagent/learning`: deterministic LearningAgent, bounded candidate generator, walk-forward evaluator, promotion gate, and workflow models.
- `finagent/validation`: multi-asset simulation adapter, leakage checks, walk-forward research workflow, transparent analyses, typed validation records, and Markdown export.
- `finagent/database`: local SQLite schema and experiment repository.
- `finagent/data`: local CSV/Yahoo historical providers, normalization, quality policy, deterministic cache manager, immutable dataset registry, and collections.
- `finagent/api`: typed FastAPI routes, request/response schemas, local settings, and OpenAPI app.
- `finagent/services`: API-facing retrieval and controlled workflow services; no research logic is duplicated here.
- `frontend`: Next.js App Router research workspace, reusable components, formats, and centralized typed API client.
- `scripts` and `dashboard`: unchanged CLI workflows and Legacy / Debug Streamlit dashboard.

## Metrics and research limits

V0.8 reports V0.1 return/trade metrics through V0.7 API/UI views plus historical data provenance and quality diagnostics. Results are historical simulations with configurable fees; they are not evidence of future performance. The public adapter is daily-only and may be unavailable, rate limited, delayed, incomplete, or differently adjusted from another provider. FinAgent records adjustment mode and warns via metadata, but does not model corporate actions, validate every exchange holiday, provide intraday/high-frequency data, or guarantee vendor completeness.

There are no LLM agents, sentiment analysis, reinforcement learning, unrestricted self-improvement, automatic parameter optimization, candidate code generation, autonomous promotion to trading, live data, paper trading, brokerage connectivity, or live trading in this version.
