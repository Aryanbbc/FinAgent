# Research methodology

FinAgent treats every output as a historical simulation. It is designed to make assumptions observable rather than to infer a future market action.

## Reproducibility

An experiment records configuration, seed, asset, date range, data path, metrics, trades, regimes, agent records, and result curves. When a registered dataset is used, the manifest also contains dataset ID/version, provider, checksum, date coverage, and adjustment metadata. Dataset revisions are immutable by checksum.

## Causality and costs

Technical features, rolling volatility, moving-average slope, momentum, and drawdown are computed from observations available at the relevant timestamp. Missing data policies never backfill from the future. Simulated position changes use configured percentage and fixed transaction costs.

## Validation evidence

V0.6 validation is opt-in. It can evaluate multiple assets, chronological walk-forward windows, leakage checks, parameter sensitivity, bootstrap confidence intervals, ablations, benchmark comparisons, and a transparent robustness score. These are diagnostics, not guarantees. Confidence intervals describe resampled historical uncertainty; they do not predict outcomes.

## Explainability

The agent chain exposes typed outputs and reason codes: technical state, regime, strategy proposal, risk approval/adjustment, critique findings, and candidate-gate results. It intentionally does not expose hidden reasoning or use an LLM.

## Interpretation

Use return, Sharpe, Sortino, drawdown, turnover, costs, benchmark comparisons, and validation evidence together. A strong single historical metric is insufficient evidence. A robustness score is a configured aggregate diagnostic, not an investability grade.
