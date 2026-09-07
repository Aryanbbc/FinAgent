# V1.0 reference results

The committed reference evaluation is `EXP-000001` with validation `VAL-000001`, created on a clean `data/release/finagent_v1.db` from `config/final_validation.yaml`. It is a deterministic release check using two short bundled CSV fixtures from 2024-01-02 through 2024-02-27. It is not evidence of expected market performance. Its manifest reports the package version, Git revision, and a `.dirty` suffix when evidence is generated before the release changes are committed.

| Measure | Result |
| --- | ---: |
| Aggregate total return | -0.34% |
| Aggregate Sharpe | -1.262 |
| Worst asset drawdown | -1.59% |
| Transaction costs | 603.82 |
| Walk-forward windows | 4 |
| Leakage checks | Passed |
| Robustness score | 0.500 |

The 95% bootstrap Sharpe interval was `-4.252` to `2.876`; it is wide because the bundled fixtures are short. The two assets produced Sharpe values of `0.323` and `-2.846`. This mixed result is intentionally retained rather than selectively presented.

The fixed benchmark export includes buy-and-hold, moving average, momentum, mean reversion, regime-aware FinAgent, multi-agent FinAgent, and critic/memory FinAgent. Critic/memory is post-experiment evidence and therefore has the same in-run path as the multi-agent comparator. `self_improved_finagent` is marked unavailable: no separately promoted out-of-sample configuration exists.

Committed portable artifacts are in [reports/v1.0](../reports/v1.0):

- `research_report.md` — full configuration, metrics, regime, critique, validation, and manifest.
- `multi_asset.csv`, `walk_forward.csv`, `sensitivity.csv`, `confidence_intervals.csv`, `ablations.csv`, and `benchmarks.csv` — final tables.
- `benchmark_total_returns.svg` — an equal-weight benchmark-return chart.
- `validation_record.json` — the typed persisted validation record.

Recreate these artifacts with:

```bash
.venv/bin/python scripts/run_validation.py --config config/final_validation.yaml
.venv/bin/python scripts/export_release_artifacts.py --experiment EXP-000001 \
  --database data/release/finagent_v1.db --output reports/v1.0
```

If the release database already contains runs, use the emitted identifiers instead of `EXP-000001`.
