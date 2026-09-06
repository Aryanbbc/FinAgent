# FinAgent V0.2

FinAgent is a reproducible quantitative-trading research and simulation platform. V0.2 preserves the V0.1 historical research engine and adds a causal, rule-based Market Regime Detection module. It loads validated CSV data, creates technical and regime features, runs baseline strategies, simulates costs and a long-only portfolio, evaluates performance, and stores experiments in SQLite.

It does **not** provide investment advice, guarantee profitability, use AI agents or reinforcement learning, analyze sentiment, or execute live trades. `LIVE_TRADING_ENABLED=false` is the default safety setting.

## Current stage

V0.2 implements the quantitative research engine plus observational rule-based market regimes. The roadmap now continues with specialized Strategy and Risk Agents (V0.3), experiment critique and memory (V0.4), and configuration-only improvement with walk-forward promotion gates (V0.5). Those later-stage components are not included yet.

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

The runner validates `data/raw/example_ohlcv.csv`, generates the configured features, detects a rule-based regime at each bar using only data available through that bar, sequentially backtests the selected strategy at each bar's close, compares it to buy-and-hold using the same cost model, and saves the experiment, trades, metrics, regime observations, configuration, seed, and equity curves to `data/finagent.db`.

Edit `config/experiments.yaml` to select `moving_average`, `momentum`, or `mean_reversion`, change their parameters, choose a local CSV, or adjust transaction costs. Required CSV columns are `timestamp`, `open`, `high`, `low`, `close`, and `volume`; timestamps must be ascending and unique.

Available baseline strategies are moving-average crossover, price momentum, and rolling-z-score mean reversion. They emit `+1` (long), `0` (hold), or `-1` (exit); V0.2 only simulates long positions.

### Regime configuration

The `regime` section of `config/default.yaml` enables V0.2 by default. It controls causal lookback windows and transparent thresholds for `bull`, `bear`, `sideways`, `high_volatility`, `low_volatility`, and `stress`. Each observation returns the primary regime, a 0–1 confidence score, and its rolling return, annualized volatility, moving-average slope, momentum, and drawdown values. Set `regime.enabled: false` to omit regime analysis for a backward-compatible V0.1-style run.

Regimes are observational in V0.2: they are not inputs to strategy selection, risk control, or execution yet.

## Dashboard

After at least one experiment has been saved, run:

```bash
streamlit run dashboard/app.py
```

The dashboard shows the latest experiment summary, key metrics, latest regime and confidence, regime-observation history/distribution, strategy-versus-buy-and-hold equity curve, and saved trade history.

## Test

```bash
python -m pytest -q
```

The tests cover invalid data, deterministic technical and regime features with causal behavior, all three strategy signals, all six regimes, accounting and costs in the backtester, performance calculations, and SQLite persistence.

## Architecture

```text
CSV OHLCV → validation → feature pipeline → strategy → sequential simulator
                    │                              ↓
                    └→ rule-based regime detector  portfolio + transaction costs
                               │                              ↓
                               └────────→ metrics + buy-and-hold benchmark
                                                           ↓
                      SQLite experiments/trades/metrics/regime observations
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
- `finagent/database`: local SQLite schema and experiment repository.
- `scripts` and `dashboard`: the user-facing runner and Streamlit dashboard.

## Metrics and research limits

V0.2 reports the V0.1 return and trade metrics plus causal regime classifications. Results are historical simulations with configurable percentage and fixed transaction fees; they are not evidence of future performance. The regime detector is intentionally heuristic and uses one primary label per bar, so it does not capture every market nuance. There are no LLM agents, sentiment analysis, reinforcement learning, strategy optimization, self-improvement, out-of-sample promotion, live data, paper trading, or brokerage connectivity in this version.
