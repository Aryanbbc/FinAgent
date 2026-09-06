"""Stable identifiers for persisted experiments."""

from __future__ import annotations


def format_experiment_id(number: int) -> str:
    if number < 1:
        raise ValueError("Experiment number must be positive")
    return f"EXP-{number:06d}"
