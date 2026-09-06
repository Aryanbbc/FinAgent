"""Typed records returned from the experiment repository."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    created_at: str
    strategy: str
    asset: str
    dataset: str
    start_date: str
    end_date: str
    starting_capital: float
    random_seed: int | None
    configuration: dict[str, Any]
    results: dict[str, Any]
