# FinAgent V0.4

FinAgent is a reproducible quantitative-trading research and simulation platform. V0.4 preserves the V0.1 historical research engine, V0.2 causal rule-based regimes, and V0.3 deterministic decision flow, then adds a post-experiment CriticAgent and Experiment Memory. It loads validated CSV data, derives causal features, simulates baseline strategies and costs, evaluates performance, and stores complete experiments in SQLite.

It does **not** provide investment advice, guarantee profitability, use AI agents or reinforcement learning, analyze sentiment, or execute live trades. `LIVE_TRADING_ENABLED=false` is the default safety setting.

## Current stage

V0.4 implements the quantitative research engine, rule-based market regimes, deterministic decision agents, evidence-based critique, and experiment memory. The roadmap now continues with V0.5 configuration-only candidate generation, walk-forward validation, and promotion gates. Those self-improvement components are not included yet.

The research goal is to evaluate whether simple, clearly specified strategies remain robust after costs and against a passive benchmark—not to optimize historical profit in isolation.

## Install

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,dashboard]'
```

Copy `.env.example` to `.env` only if you need local environment settings; V0.1 does not require any credentials.

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

The critic is descriptive only. Its recommendations never modify parameters, strategies, risk limits, or execution. To preserve V0.1–V0.3-style runs, set `critic.enabled: false`.

## Dashboard

After at least one experiment has been saved, run:

```bash
streamlit run dashboard/app.py
```

The dashboard shows the latest experiment summary, key metrics, latest regime and agent decision, the V0.4 Experiment Critique section, regime/agent histories, strategy-versus-buy-and-hold equity curve, and saved trade history.

## Test

```bash
python -m pytest -q
```

The tests cover invalid data, causal technical/regime behavior, all three strategies, all six regimes, V0.3 agents/risk gating, deterministic critique findings, memory persistence/retrieval, configuration compatibility, accounting/costs, metrics, and SQLite persistence.

## Architecture

```text
CSV OHLCV → validation → feature pipeline → TechnicalAgent → StrategyAgent → RiskAgent → simulator
                    │                         │                │                │
                    └→ rule-based detector → RegimeAgent ──────┘                │
                                                            portfolio + transaction costs
                                                                        ↓
                                                   metrics + buy-and-hold benchmark
                                                                        ↓
                              CriticAgent → Experiment Memory (post-experiment only)
                                                                        ↓
             SQLite experiments/trades/metrics/regimes/agent decisions/critiques/memory
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
- `finagent/database`: local SQLite schema and experiment repository.
- `scripts` and `dashboard`: the user-facing runner and Streamlit dashboard.

## Metrics and research limits

V0.4 reports V0.1 return/trade metrics, V0.2 causal regimes, V0.3 agent decisions, and V0.4 critique/memory. Results are historical simulations with configurable fees; they are not evidence of future performance. Regime, agent, and critic policies are intentionally heuristic. Critique recommendations are evidence prompts for later manual research, not automatic improvements. There are no LLM agents, sentiment analysis, reinforcement learning, strategy optimization, self-improvement, candidate generation, promotion gates, live data, paper trading, or brokerage connectivity in this version.
