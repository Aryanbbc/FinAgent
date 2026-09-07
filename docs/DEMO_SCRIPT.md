# Five-minute demonstration script

1. Run `make check-env` and state that all components use historical data only.
2. Run `.venv/bin/python scripts/seed_demo.py`, then `make dev`.
3. Open the Dashboard. Point out the costs, drawdown, regime timeline, agent decision, critic result, and explicit simulation warning.
4. Open Data to show provenance, checksum, quality diagnostics, and immutable revisions.
5. Open Validation to show multi-asset results, non-overlapping walk-forward windows, sensitivity, ablation, confidence intervals, and leakage status.
6. Run `.venv/bin/python scripts/run_validation.py --config config/final_validation.yaml` and record the emitted experiment and validation IDs.
7. Run `scripts/export_release_artifacts.py` with that experiment ID; open `reports/v1.0/benchmark_total_returns.svg` and `research_report.md`.
8. Close by stating that no live/paper trading, broker integration, LLM, reinforcement learning, sentiment analysis, authentication, or payments are present.
