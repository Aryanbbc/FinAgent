from __future__ import annotations

import pandas as pd

from finagent.database.db import Database
from finagent.database.experiment_repository import ExperimentRepository


def test_repository_persists_experiment_trades_and_metrics(tmp_path) -> None:
    repository = ExperimentRepository(Database(tmp_path / "finagent.db"))
    trades = pd.DataFrame(
        [
            {
                "timestamp": "2024-01-01T00:00:00+00:00",
                "side": "BUY",
                "price": 100.0,
                "quantity": 1.0,
                "transaction_cost": 1.0,
                "portfolio_value": 99.0,
                "realized_pnl": None,
                "trade_return": None,
            }
        ]
    )
    experiment_id = repository.save_experiment(
        strategy="momentum",
        asset="TEST",
        dataset="test.csv",
        start_date="2024-01-01",
        end_date="2024-01-02",
        starting_capital=100.0,
        random_seed=42,
        configuration={"strategy": {"name": "momentum"}},
        results={"metrics": {"total_return": 0.1}},
        metrics={"total_return": 0.1},
        trades=trades,
    )
    saved = repository.get_experiment(experiment_id)
    assert experiment_id == "EXP-000001"
    assert saved is not None
    assert saved.asset == "TEST"
    assert saved.configuration["strategy"]["name"] == "momentum"
    assert repository.get_trades(experiment_id).iloc[0]["side"] == "BUY"
    assert repository.latest_experiment().experiment_id == experiment_id
