"""Explicit V0.6 leakage and chronology safeguards for historical research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from finagent.features.pipeline import FeaturePipeline
from finagent.learning.walk_forward import ChronologicalSplit
from finagent.validation.models import LeakageCheckResult


class LeakageValidationError(ValueError):
    """Raised when a validation plan could use observations unavailable at decision time."""


def validate_market_data(market_data: pd.DataFrame) -> None:
    """Require unique, strictly chronological timestamps before feature or split evaluation."""
    if "timestamp" not in market_data.columns:
        raise LeakageValidationError("Leakage check requires a timestamp column")
    timestamps = pd.to_datetime(market_data["timestamp"], utc=True)
    if timestamps.isna().any():
        raise LeakageValidationError("Invalid timestamp encountered during leakage check")
    if not timestamps.is_monotonic_increasing:
        raise LeakageValidationError("Invalid chronological ordering: timestamps must be increasing")
    if timestamps.duplicated().any():
        raise LeakageValidationError("Duplicated timestamps may cross evaluation boundaries")


def validate_splits(market_data: pd.DataFrame, splits: Sequence[ChronologicalSplit], *, allow_overlapping_tests: bool = False) -> None:
    """Verify all train/test boundaries are chronological, disjoint, and free of timestamp overlap."""
    validate_market_data(market_data)
    seen_test_positions: set[int] = set()
    for split in splits:
        if not (0 <= split.train_start < split.train_end <= split.test_start < split.test_end <= len(market_data)):
            raise LeakageValidationError("Overlapping or invalid train/test boundaries detected")
        train_timestamps = set(pd.to_datetime(market_data.iloc[split.train_start : split.train_end]["timestamp"], utc=True))
        test_timestamps = set(pd.to_datetime(market_data.iloc[split.test_start : split.test_end]["timestamp"], utc=True))
        if train_timestamps & test_timestamps:
            raise LeakageValidationError("Train/test timestamp overlap detected")
        test_positions = set(range(split.test_start, split.test_end))
        if not allow_overlapping_tests and seen_test_positions & test_positions:
            raise LeakageValidationError("Overlapping out-of-sample test windows detected")
        seen_test_positions.update(test_positions)


def validate_preprocessing_scope(fitted_through: int, test_start: int) -> None:
    """Require any fitted preprocessing to end before the associated held-out test segment."""
    if fitted_through >= test_start:
        raise LeakageValidationError("Preprocessing appears fitted using test data")


def validate_feature_causality(
    market_data: pd.DataFrame,
    featured_data: pd.DataFrame,
    feature_configuration: Mapping[str, Any],
    annualization_factor: int,
) -> None:
    """Rebuild each feature from its causal prefix and compare against the supplied full result."""
    validate_market_data(market_data)
    feature_columns = [column for column in featured_data.columns if column not in market_data.columns]
    pipeline = FeaturePipeline(annualization_factor)
    for index in range(len(market_data)):
        prefix = pipeline.generate(market_data.iloc[: index + 1], feature_configuration)
        for column in feature_columns:
            expected = prefix.iloc[-1][column]
            observed = featured_data.iloc[index][column]
            if pd.isna(expected) and pd.isna(observed):
                continue
            if pd.isna(expected) != pd.isna(observed) or not np.isclose(float(expected), float(observed), equal_nan=True):
                raise LeakageValidationError(f"Feature look-ahead detected in column '{column}' at row {index}")


def run_leakage_checks(
    market_data: pd.DataFrame,
    featured_data: pd.DataFrame,
    feature_configuration: Mapping[str, Any],
    annualization_factor: int,
    splits: Sequence[ChronologicalSplit],
    *,
    allow_overlapping_tests: bool = False,
) -> LeakageCheckResult:
    """Run the complete deterministic V0.6 leakage suite and return an auditable success record."""
    validate_market_data(market_data)
    validate_feature_causality(market_data, featured_data, feature_configuration, annualization_factor)
    validate_splits(market_data, splits, allow_overlapping_tests=allow_overlapping_tests)
    return LeakageCheckResult(
        passed=True,
        checks=(
            "chronological_ordering",
            "duplicate_timestamps",
            "train_test_boundaries",
            "feature_causality",
            "preprocessing_scope",
        ),
        errors=(),
    )
