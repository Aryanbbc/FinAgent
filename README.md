# FinAgent V0.5

FinAgent is a reproducible quantitative-trading research and simulation platform. V0.5 preserves the V0.1 historical research engine, V0.2 causal rule-based regimes, V0.3 deterministic decision flow, and V0.4 critique/memory. It adds a user-invoked, constrained configuration-improvement loop: deterministic candidate generation, chronological walk-forward validation, a risk-aware promotion gate, and an immutable version registry.

It does **not** provide investment advice, guarantee profitability, use AI agents or reinforcement learning, analyze sentiment, or execute live trades. `LIVE_TRADING_ENABLED=false` is the default safety setting.

## Current stage

V0.5 implements the quantitative research engine, rule-based market regimes, deterministic decision agents, evidence-based critique/memory, and controlled candidate evaluation. It may select a new saved configuration only after out-of-sample, risk-adjusted validation; it never rewrites code, changes a running experiment, or triggers execution.

The research goal is to evaluate whether simple, clearly specified strategies remain robust after costs and against a passive benchmark—not to optimize historical profit in isolation. Promotion is based on held-out Sharpe, drawdown, return, consistency, turnover, costs, and minimum trade count.

## Install

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,dashboard]'
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

## Dashboard

After at least one experiment has been saved, run:

```bash
streamlit run dashboard/app.py
```

The dashboard shows the latest experiment summary, key metrics, latest regime and agent decision, the V0.4 Experiment Critique section, regime/agent histories, strategy-versus-buy-and-hold equity curve, and saved trade history. Once an improvement cycle has run, its **Self-Improvement** section also shows the current version, parent/candidate, latest promotion or rejection, reason codes, candidate changes, each walk-forward test window, and evolution history.

## Test

```bash
python -m pytest -q
```

The tests cover invalid data, causal technical/regime behavior, all three strategies, all six regimes, V0.3 agents/risk gating, deterministic critique findings, memory persistence/retrieval, configuration compatibility, accounting/costs, metrics, SQLite persistence, V0.5 allowlist constraints, reproducible candidates, walk-forward chronology/no-look-ahead behavior, promotion/rejection, immutable versions, and the disabled compatibility path.

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
                                                             CLI and Streamlit dashboard
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
- `finagent/database`: local SQLite schema and experiment repository.
- `scripts` and `dashboard`: the user-facing runner and Streamlit dashboard.

## Metrics and research limits

V0.5 reports V0.1 return/trade metrics, V0.2 causal regimes, V0.3 agent decisions, V0.4 critique/memory, and V0.5 saved validation/promotion evidence. Results are historical simulations with configurable fees; they are not evidence of future performance. Regime, agent, critic, and LearningAgent policies are intentionally heuristic. V0.5 mitigates overfitting through bounded changes and held-out chronological tests, but small data sets, fixed rules, limited candidate surfaces, and historical regime shifts remain material limitations.

There are no LLM agents, sentiment analysis, reinforcement learning, unrestricted self-improvement, automatic parameter optimization, candidate code generation, autonomous promotion to trading, live data, paper trading, brokerage connectivity, or live trading in this version.
