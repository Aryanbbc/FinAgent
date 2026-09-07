# Research methodology

FinAgent treats every output as a historical simulation. It is designed to make assumptions observable rather than to infer a future market action.

## Reproducibility

An experiment records configuration, seed, asset, date range, data path, metrics, trades, regimes, agent records, and result curves. When a registered dataset is used, the manifest also contains dataset ID/version, provider, checksum, date coverage, and adjustment metadata. Dataset revisions are immutable by checksum.

## Causality and costs

Technical features, rolling volatility, moving-average slope, momentum, and drawdown are computed from observations available at the relevant timestamp. Missing data policies never backfill from the future. Simulated position changes use configured percentage and fixed transaction costs.

## Validation evidence

V0.6 validation is opt-in. It can evaluate multiple assets, chronological walk-forward windows, leakage checks, parameter sensitivity, bootstrap confidence intervals, ablations, benchmark comparisons, and a transparent robustness score. These are diagnostics, not guarantees. Confidence intervals describe resampled historical uncertainty; they do not predict outcomes.

## V1.0 final reference suite

`config/final_validation.yaml` fixes a V1.0 reference run: two bundled, content-addressable CSV fixtures; rolling non-overlapping 15/10-observation train/test windows; explicit costs; six sensitivity points; 500 deterministic bootstrap samples; five ablations; and the final benchmark labels. The source configuration enables regimes, the deterministic multi-agent chain, and critic/memory evidence. It keeps learning disabled.

The fixtures are deliberately short and bundled so a clean clone can reproduce the exact workflow without network access. They are release fixtures—not a sufficiently broad dataset for a claim about a real market or future performance. A self-improved benchmark is unavailable unless a separately promoted out-of-sample configuration exists; the suite never creates one from the release data.

The export step reads the persisted validation record and writes a Markdown report, tabular CSV files, a simple SVG chart, and a JSON record. This preserves a separation between evaluating and reporting evidence.

## Explainability

The agent chain exposes typed outputs and reason codes: technical state, regime, strategy proposal, risk approval/adjustment, critique findings, and candidate-gate results. It intentionally does not expose hidden reasoning or use an LLM.

## Interpretation

Use return, Sharpe, Sortino, drawdown, turnover, costs, benchmark comparisons, and validation evidence together. A strong single historical metric is insufficient evidence. A robustness score is a configured aggregate diagnostic, not an investability grade.
