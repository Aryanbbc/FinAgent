# FinAgent V0.1

FinAgent is a reproducible quantitative-trading research and simulation platform. V0.1 is deliberately limited to local historical OHLCV research: it loads validated CSV data, creates causal technical features, runs baseline strategies, simulates costs and a long-only portfolio, evaluates performance, and stores experiments in SQLite.

It does **not** provide investment advice, guarantee profitability, use AI agents or reinforcement learning, analyze sentiment, or execute live trades. `LIVE_TRADING_ENABLED=false` is the default safety setting.

## Current stage

V0.1 implements the quantitative research engine. The subsequent roadmap is rule-based market regimes (V0.2), specialized decision/risk agents (V0.3), experiment critique and memory (V0.4), and configuration-only improvement with walk-forward promotion gates (V0.5). None of those later-stage components are included yet.

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

The runner validates `data/raw/example_ohlcv.csv`, generates the configured features, sequentially backtests the selected strategy at each bar's close, compares it to buy-and-hold using the same cost model, and saves the experiment, trades, metrics, configuration, seed, and equity curves to `data/finagent.db`.

Edit `config/experiments.yaml` to select `moving_average`, `momentum`, or `mean_reversion`, change their parameters, choose a local CSV, or adjust transaction costs. Required CSV columns are `timestamp`, `open`, `high`, `low`, `close`, and `volume`; timestamps must be ascending and unique.

Available baseline strategies are moving-average crossover, price momentum, and rolling-z-score mean reversion. They emit `+1` (long), `0` (hold), or `-1` (exit); V0.1 only simulates long positions.

## Dashboard

After at least one experiment has been saved, run:

```bash
streamlit run dashboard/app.py
```

The dashboard shows the latest experiment summary, key metrics, strategy-versus-buy-and-hold equity curve, and saved trade history.

## Test

```bash
python -m pytest -q
```

The tests cover invalid data, deterministic technical features and their causal behavior, all three strategy signals, accounting and costs in the backtester, performance calculations, and SQLite persistence.

## Architecture

```text
CSV OHLCV → validation → feature pipeline → strategy → sequential simulator
                                                   ↓
                                      portfolio + transaction costs
                                                   ↓
                                  metrics + buy-and-hold benchmark
                                                   ↓
                                      SQLite experiments/trades/metrics
                                                   ↓
                                         CLI and Streamlit dashboard
```

Key source directories:

- `finagent/data`: provider interface, CSV loader, strict OHLCV validator.
- `finagent/features`: configurable, look-ahead-safe technical indicators.
- `finagent/strategies`: moving-average, momentum, and mean-reversion baselines.
- `finagent/backtesting`: cost model, execution sizing, portfolio accounting, and causal engine.
- `finagent/evaluation`: performance metrics and buy-and-hold benchmark.
- `finagent/database`: local SQLite schema and experiment repository.
- `scripts` and `dashboard`: the user-facing runner and Streamlit dashboard.

## Metrics and research limits

V0.1 reports total/cumulative and annualized return, annualized volatility, Sharpe and Sortino ratios, maximum drawdown, closed-trade count, win rate, average trade return, profit factor where defined, and turnover. Results are historical simulations with configurable percentage and fixed transaction fees; they are not evidence of future performance. There is no automatic optimization, out-of-sample promotion, live data, or brokerage connectivity in this version.
