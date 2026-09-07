# FinAgent Research Report — EXP-000001

## Experiment Summary

- Strategy: `momentum`
- Asset: `BUNDLED_PRIMARY`
- Dataset: `data/raw/example_ohlcv.csv`
- Dates: 2024-01-02 to 2024-02-27
- Starting capital: 100000.00

## Configuration

```json
{
  "agents": {
    "enabled": true,
    "risk": {
      "max_drawdown": 0.2,
      "max_position_size": 1.0,
      "max_volatility": 0.5,
      "minimum_confidence": 0.15,
      "reduced_position_size": 0.5,
      "reduced_volatility_threshold": 0.3
    },
    "strategy": {
      "available_strategies": {
        "mean_reversion": {
          "entry_zscore": -1.0,
          "exit_zscore": 0.0,
          "lookback_window": 10
        },
        "momentum": {
          "entry_threshold": 0.0,
          "exit_threshold": -0.02,
          "lookback_window": 5
        },
        "moving_average": {
          "fast_window": 5,
          "slow_window": 20
        }
      },
      "regime_strategy_map": {
        "bear": "moving_average",
        "bull": "momentum",
        "high_volatility": "moving_average",
        "low_volatility": "mean_reversion",
        "sideways": "mean_reversion",
        "stress": "moving_average"
      },
      "strategy_weights": {}
    },
    "technical": {
      "high_volatility_threshold": 0.3,
      "low_volatility_threshold": 0.1,
      "momentum_threshold": 0.005,
      "overbought_rsi": 70.0,
      "oversold_rsi": 30.0,
      "trend_threshold": 0.003
    }
  },
  "application": {
    "live_trading_enabled": false,
    "name": "FinAgent",
    "version": "1.0.0"
  },
  "backtest": {
    "annualization_factor": 252,
    "position_fraction": 1.0,
    "transaction_costs": {
      "fixed_fee": 1.0,
      "percentage_fee": 0.001
    }
  },
  "critic": {
    "enabled": true,
    "thresholds": {
      "controlled_drawdown_threshold": 0.1,
      "excessive_turnover_threshold": 2.0,
      "high_drawdown_threshold": 0.15,
      "high_transaction_cost_ratio": 0.01,
      "low_turnover_threshold": 0.5,
      "minimum_closed_trades": 3,
      "strong_sharpe_threshold": 1.0,
      "weak_sharpe_threshold": 0.0
    }
  },
  "data": {
    "cache_path": "data/cache",
    "missing_data_policy": "reject"
  },
  "database_path": "data/release/finagent_v1.db",
  "experiment": {
    "asset": "BUNDLED_PRIMARY",
    "dataset": "data/raw/example_ohlcv.csv",
    "random_seed": 42,
    "starting_capital": 100000.0
  },
  "features": {
    "ema": {
      "span": 5
    },
    "log_return": true,
    "momentum": {
      "window": 5
    },
    "rolling_volatility": {
      "window": 10
    },
    "rolling_volume_mean": {
      "window": 10
    },
    "rsi": {
      "window": 14
    },
    "simple_return": true,
    "sma": {
      "window": 5
    },
    "volume_change": true
  },
  "learning": {
    "enabled": false
  },
  "market": {
    "annualization_factor": 252
  },
  "regime": {
    "drawdown_window": 20,
    "enabled": true,
    "momentum_window": 5,
    "moving_average_slope_window": 5,
    "moving_average_window": 10,
    "return_window": 10,
    "thresholds": {
      "bear_return_threshold": -0.02,
      "bull_return_threshold": 0.02,
      "high_volatility_threshold": 0.3,
      "low_volatility_threshold": 0.1,
      "moving_average_slope_threshold": 0.003,
      "stress_drawdown_threshold": -0.12
    },
    "volatility_window": 10
  },
  "release": {
    "dataset_suite": "bundled_two_asset_fixture",
    "name": "v1.0.0-final-reference",
    "purpose": "deterministic historical-release verification"
  },
  "strategy": {
    "name": "momentum",
    "parameters": {
      "entry_threshold": 0.0,
      "exit_threshold": -0.02,
      "lookback_window": 5
    }
  },
  "validation": {
    "enabled": false
  }
}
```

## Primary Metrics

| Return | Sharpe | Sortino | Max drawdown | Turnover | Transaction costs | Trades |
|---:|---:|---:|---:|---:|---:|---:|
| 0.23% | 0.323 | 0.285 | -1.59% | 3.986 | 402.80 | 2 |

## Regime and Agent Summary

- Regime distribution: `{'sideways': 34, 'bull': 6}`
- Agent observations: 40

## Critique Summary

- Confidence: 0.86
- Strengths: POSITIVE_RETURN, CONTROLLED_DRAWDOWN
- Weaknesses: UNDERPERFORMS_BENCHMARK, EXCESSIVE_TURNOVER, LOW_TRADE_SAMPLE

## Research Validation

- Validation ID: `VAL-000001`
- Leakage checks: passed

### Multi-Asset Summary

| Asset | Return | Sharpe | Max drawdown | Passed |
|---|---:|---:|---:|---|
| BUNDLED_PRIMARY | 0.23% | 0.323 | -1.59% | True |
| BUNDLED_SECONDARY | -0.91% | -2.846 | -0.91% | True |

### Aggregate Metrics

| Return | Sharpe | Sortino | Max drawdown | Turnover | Transaction costs | Trades |
|---:|---:|---:|---:|---:|---:|---:|
| -0.34% | -1.262 | -0.228 | -1.59% | 2.991 | 603.82 | 3 |

### Robustness Score

- Overall score: 0.500
- asset_consistency: 0.300
- benchmark_consistency: 0.000
- drawdown_control: 0.947
- sensitivity_stability: 1.000
- turnover_stability: 0.751
- window_consistency: 0.000

### Confidence Intervals (estimated)

| Metric | Estimate | Lower | Upper | Level | Samples |
|---|---:|---:|---:|---:|---:|
| mean_return | -0.000 | -0.001 | 0.000 | 95% | 500 |
| sharpe_ratio | -0.551 | -4.252 | 2.876 | 95% | 500 |

### Walk-Forward Results

| Asset | Window | Mode | Test dates | Return | Sharpe | Max drawdown |
|---|---:|---|---|---:|---:|---:|
| BUNDLED_PRIMARY | 1 | rolling | 2024-01-23 to 2024-02-05 | 0.15% | 0.463 | -1.59% |
| BUNDLED_PRIMARY | 2 | rolling | 2024-02-06 to 2024-02-20 | 0.08% | 0.424 | -0.65% |
| BUNDLED_SECONDARY | 1 | rolling | 2024-01-23 to 2024-02-05 | 0.00% | N/A | 0.00% |
| BUNDLED_SECONDARY | 2 | rolling | 2024-02-06 to 2024-02-20 | -0.91% | -5.681 | -0.91% |

### Sensitivity Analysis

| Parameter | Value | Sharpe | Return | Max drawdown | Turnover | Costs | Stability |
|---|---:|---:|---:|---:|---:|---:|---:|
| momentum_window | 4 | -1.262 | -0.34% | -1.59% | 2.991 | 603.82 | 1.000 |
| momentum_window | 5 | -1.262 | -0.34% | -1.59% | 2.991 | 603.82 | 1.000 |
| momentum_window | 6 | -1.262 | -0.34% | -1.59% | 2.991 | 603.82 | 1.000 |
| risk_confidence_threshold | 0.1 | -1.262 | -0.34% | -1.59% | 2.991 | 603.82 | 1.000 |
| risk_confidence_threshold | 0.15 | -1.262 | -0.34% | -1.59% | 2.991 | 603.82 | 1.000 |
| risk_confidence_threshold | 0.2 | -1.262 | -0.34% | -1.59% | 2.991 | 603.82 | 1.000 |

### Ablation Study

| Variant | Return | Sharpe | Sortino | Max drawdown | Turnover | Costs | Robustness |
|---|---:|---:|---:|---:|---:|---:|---:|
| A: baseline strategy only | 0.64% | 0.463 | 1.840 | -5.01% | 3.961 | 803.67 | 0.449 |
| B: + regime detection | 0.64% | 0.463 | 1.840 | -5.01% | 3.961 | 803.67 | 0.449 |
| C: + multi-agent decision system | -0.34% | -1.262 | -0.228 | -1.59% | 2.991 | 603.82 | 0.500 |
| D: + critic/memory | -0.34% | -1.262 | -0.228 | -1.59% | 2.991 | 603.82 | 0.500 |
| E: + self-improvement | -0.34% | -1.262 | -0.228 | -1.59% | 2.991 | 603.82 | 0.500 |

### Benchmark Suite

| Asset | Benchmark | Status | Return | Sharpe | Max drawdown |
|---|---|---|---:|---:|---:|
| BUNDLED_PRIMARY | buy_and_hold | available | 9.24% | 4.577 | -2.92% |
| BUNDLED_PRIMARY | moving_average | available | 3.77% | 2.797 | -2.92% |
| BUNDLED_PRIMARY | momentum | available | 3.12% | 1.836 | -3.11% |
| BUNDLED_PRIMARY | mean_reversion | available | 1.95% | 3.427 | -0.10% |
| BUNDLED_PRIMARY | regime_aware_finagent | available | 3.12% | 1.836 | -3.11% |
| BUNDLED_PRIMARY | multi_agent_finagent | available | 0.23% | 0.323 | -1.59% |
| BUNDLED_PRIMARY | critic_memory_finagent | available | 0.23% | 0.323 | -1.59% |
| BUNDLED_PRIMARY | self_improved_finagent | no_promoted_configuration | N/A | N/A | N/A |
| BUNDLED_SECONDARY | buy_and_hold | available | 4.74% | 2.053 | -3.78% |
| BUNDLED_SECONDARY | moving_average | available | -2.97% | -2.416 | -4.39% |
| BUNDLED_SECONDARY | momentum | available | -1.85% | -0.910 | -5.01% |
| BUNDLED_SECONDARY | mean_reversion | available | 5.25% | 5.138 | -0.84% |
| BUNDLED_SECONDARY | regime_aware_finagent | available | -1.85% | -0.910 | -5.01% |
| BUNDLED_SECONDARY | multi_agent_finagent | available | -0.91% | -2.846 | -0.91% |
| BUNDLED_SECONDARY | critic_memory_finagent | available | -0.91% | -2.846 | -0.91% |
| BUNDLED_SECONDARY | self_improved_finagent | no_promoted_configuration | N/A | N/A | N/A |

## Reproducibility Manifest

```json
{
  "assets": [
    "BUNDLED_PRIMARY",
    "BUNDLED_SECONDARY"
  ],
  "code_version": "1.0.0+721eda1.dirty",
  "configuration": {
    "agents": {
      "enabled": true,
      "risk": {
        "max_drawdown": 0.2,
        "max_position_size": 1.0,
        "max_volatility": 0.5,
        "minimum_confidence": 0.15,
        "reduced_position_size": 0.5,
        "reduced_volatility_threshold": 0.3
      },
      "strategy": {
        "available_strategies": {
          "mean_reversion": {
            "entry_zscore": -1.0,
            "exit_zscore": 0.0,
            "lookback_window": 10
          },
          "momentum": {
            "entry_threshold": 0.0,
            "exit_threshold": -0.02,
            "lookback_window": 5
          },
          "moving_average": {
            "fast_window": 5,
            "slow_window": 20
          }
        },
        "regime_strategy_map": {
          "bear": "moving_average",
          "bull": "momentum",
          "high_volatility": "moving_average",
          "low_volatility": "mean_reversion",
          "sideways": "mean_reversion",
          "stress": "moving_average"
        },
        "strategy_weights": {}
      },
      "technical": {
        "high_volatility_threshold": 0.3,
        "low_volatility_threshold": 0.1,
        "momentum_threshold": 0.005,
        "overbought_rsi": 70.0,
        "oversold_rsi": 30.0,
        "trend_threshold": 0.003
      }
    },
    "application": {
      "live_trading_enabled": false,
      "name": "FinAgent",
      "version": "1.0.0"
    },
    "backtest": {
      "annualization_factor": 252,
      "position_fraction": 1.0,
      "transaction_costs": {
        "fixed_fee": 1.0,
        "percentage_fee": 0.001
      }
    },
    "critic": {
      "enabled": true,
      "thresholds": {
        "controlled_drawdown_threshold": 0.1,
        "excessive_turnover_threshold": 2.0,
        "high_drawdown_threshold": 0.15,
        "high_transaction_cost_ratio": 0.01,
        "low_turnover_threshold": 0.5,
        "minimum_closed_trades": 3,
        "strong_sharpe_threshold": 1.0,
        "weak_sharpe_threshold": 0.0
      }
    },
    "data": {
      "cache_path": "data/cache",
      "missing_data_policy": "reject"
    },
    "database_path": "data/release/finagent_v1.db",
    "experiment": {
      "asset": "BUNDLED_PRIMARY",
      "dataset": "data/raw/example_ohlcv.csv",
      "random_seed": 42,
      "starting_capital": 100000.0
    },
    "features": {
      "ema": {
        "span": 5
      },
      "log_return": true,
      "momentum": {
        "window": 5
      },
      "rolling_volatility": {
        "window": 10
      },
      "rolling_volume_mean": {
        "window": 10
      },
      "rsi": {
        "window": 14
      },
      "simple_return": true,
      "sma": {
        "window": 5
      },
      "volume_change": true
    },
    "learning": {
      "enabled": false
    },
    "market": {
      "annualization_factor": 252
    },
    "regime": {
      "drawdown_window": 20,
      "enabled": true,
      "momentum_window": 5,
      "moving_average_slope_window": 5,
      "moving_average_window": 10,
      "return_window": 10,
      "thresholds": {
        "bear_return_threshold": -0.02,
        "bull_return_threshold": 0.02,
        "high_volatility_threshold": 0.3,
        "low_volatility_threshold": 0.1,
        "moving_average_slope_threshold": 0.003,
        "stress_drawdown_threshold": -0.12
      },
      "volatility_window": 10
    },
    "release": {
      "dataset_suite": "bundled_two_asset_fixture",
      "name": "v1.0.0-final-reference",
      "purpose": "deterministic historical-release verification"
    },
    "strategy": {
      "name": "momentum",
      "parameters": {
        "entry_threshold": 0.0,
        "exit_threshold": -0.02,
        "lookback_window": 5
      }
    },
    "validation": {
      "enabled": false
    }
  },
  "created_at": "2026-09-07T04:47:17.255742+00:00",
  "datasets": [
    {
      "bytes": 1755,
      "dataset": "data/raw/example_ohlcv.csv",
      "sha256": "cc5ff592be7b8d64c241ff93b098c89bde25effce7390bab664f1fcfad8cf376"
    },
    {
      "bytes": 1590,
      "dataset": "data/raw/example_ohlcv_secondary.csv",
      "sha256": "95063c1cf10cef34d8667dddec522f490e8a8a50de45b8467c5e29c8d903dd92"
    }
  ],
  "date_ranges": {
    "BUNDLED_PRIMARY": {
      "end": "2024-02-27",
      "start": "2024-01-02"
    },
    "BUNDLED_SECONDARY": {
      "end": "2024-02-27",
      "start": "2024-01-02"
    }
  },
  "enabled_modules": {
    "agents": true,
    "critic": true,
    "learning": false,
    "regime": true
  },
  "evaluation_mode": "multi_asset",
  "experiment_id": "EXP-000001",
  "random_seeds": {
    "bootstrap": 42,
    "experiment": 42
  },
  "transaction_costs": {
    "fixed_fee": 1.0,
    "percentage_fee": 0.001
  },
  "walk_forward": {
    "min_windows": 2,
    "minimum_test_length": 10,
    "minimum_train_length": 15,
    "non_overlapping_test_windows": true,
    "step_size": 10,
    "test_size": 10,
    "train_size": 15,
    "window_mode": "rolling"
  }
}
```

## Self-Improvement History

| Version | Parent | Candidate | Status |
|---|---|---|---|
| None | | | |

## Limitations

- All results are historical simulations and do not establish future performance or investment suitability.
- Bootstrap intervals are estimated from observed returns; they do not account for regime changes, dependence, or model uncertainty.
- Robustness is a transparent heuristic score, not a statistical proof of generalization.
- FinAgent remains local, deterministic, and research-only: no LLMs, live data, paper trading, or brokerage execution.
