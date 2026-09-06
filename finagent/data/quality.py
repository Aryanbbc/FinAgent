"""Transparent data-quality diagnostics and conservative missing-data policies."""

from __future__ import annotations

import pandas as pd

from finagent.data.models import (
    DataQualityScore,
    DataValidationIssue,
    DatasetValidationResult,
    MissingDataPolicy,
    ValidationStatus,
)
from finagent.data.normalization import OHLCVNormalizer
from finagent.data.validator import DataValidationError, OHLCVValidator, REQUIRED_OHLCV_COLUMNS


class DataValidationPipeline:
    """Assesses quality before applying a deliberately explicit, non-look-ahead repair policy."""

    def __init__(self, max_gap_days: int = 7) -> None:
        self.max_gap_days = max_gap_days
        self.normalizer = OHLCVNormalizer()
        self.strict_validator = OHLCVValidator()

    def assess(self, frame: pd.DataFrame, policy: MissingDataPolicy = MissingDataPolicy.REJECT) -> DatasetValidationResult:
        normalized = self.normalizer.normalize(frame)
        issues = self._issues(normalized)
        components, gap_count = self._components(normalized, issues)
        has_error = any(item.severity == "error" for item in issues)
        status = ValidationStatus.INVALID if has_error else (ValidationStatus.WARNING if issues else ValidationStatus.VALID)
        score_inputs = (
            components["completeness"], 1 - components["duplicate_rate"], 1 - components["nan_rate"],
            components["chronological_consistency"], components["ohlc_validity"], 1 - components["gap_severity"],
            components["timezone_consistency"],
        )
        return DatasetValidationResult(status, tuple(issues), DataQualityScore(sum(score_inputs) / len(score_inputs), components, gap_count), policy)

    def prepare(self, frame: pd.DataFrame, policy: MissingDataPolicy = MissingDataPolicy.REJECT) -> tuple[pd.DataFrame, DatasetValidationResult]:
        """Return canonical OHLCV or fail safely according to the selected policy."""
        normalized = self.normalizer.normalize(frame)
        result = self.assess(normalized, policy)
        if result.status == ValidationStatus.INVALID:
            if policy == MissingDataPolicy.REJECT:
                errors = "; ".join(item.message for item in result.issues if item.severity == "error")
                raise DataValidationError(errors)
            if policy == MissingDataPolicy.DROP:
                normalized = normalized.dropna().drop_duplicates(subset="timestamp", keep="first").reset_index(drop=True)
            elif policy == MissingDataPolicy.FORWARD_FILL:
                # Forward fill uses only prior observations; no future values are introduced.
                normalized = normalized.drop_duplicates(subset="timestamp", keep="first").sort_values("timestamp", kind="stable")
                normalized.loc[:, ["open", "high", "low", "close", "volume"]] = normalized.loc[:, ["open", "high", "low", "close", "volume"]].ffill()
                normalized = normalized.dropna().reset_index(drop=True)
            elif policy == MissingDataPolicy.WARN_ONLY:
                return normalized, result
            result = self.assess(normalized, policy)
            if result.status == ValidationStatus.INVALID:
                errors = "; ".join(item.message for item in result.issues if item.severity == "error")
                raise DataValidationError(errors)
        return self.strict_validator.validate(normalized), result

    def _issues(self, frame: pd.DataFrame) -> list[DataValidationIssue]:
        issues: list[DataValidationIssue] = []
        nulls = int(frame.loc[:, list(REQUIRED_OHLCV_COLUMNS)].isna().sum().sum())
        if nulls:
            issues.append(DataValidationIssue("NAN_VALUES", "error", "OHLCV contains missing or non-numeric values.", nulls))
        duplicates = int(frame["timestamp"].duplicated().sum())
        if duplicates:
            issues.append(DataValidationIssue("DUPLICATE_TIMESTAMPS", "error", "OHLCV contains duplicate timestamps.", duplicates))
        if not frame["timestamp"].is_monotonic_increasing:
            issues.append(DataValidationIssue("CHRONOLOGICAL_ORDER", "error", "Timestamps are not chronologically ordered.", 1))
        prices = frame[["open", "high", "low", "close"]]
        non_positive = int((prices <= 0).sum().sum())
        if non_positive:
            issues.append(DataValidationIssue("NON_POSITIVE_PRICE", "error", "OHLC prices must be positive.", non_positive))
        negative_volume = int((frame["volume"] < 0).sum())
        if negative_volume:
            issues.append(DataValidationIssue("NEGATIVE_VOLUME", "error", "Volume cannot be negative.", negative_volume))
        high_invalid = frame["high"] < frame[["open", "low", "close"]].max(axis=1)
        low_invalid = frame["low"] > frame[["open", "high", "close"]].min(axis=1)
        invalid_ohlc = int((high_invalid | low_invalid).sum())
        if invalid_ohlc:
            issues.append(DataValidationIssue("INVALID_OHLC", "error", "High/low bounds are inconsistent.", invalid_ohlc))
        gaps = self._gap_count(frame)
        if gaps:
            issues.append(DataValidationIssue("SUSPICIOUS_GAPS", "warning", f"Detected timestamp gaps larger than {self.max_gap_days} days.", gaps))
        if not isinstance(frame["timestamp"].dtype, pd.DatetimeTZDtype):
            issues.append(DataValidationIssue("TIMEZONE_INCONSISTENT", "warning", "Timestamps are not timezone-aware UTC values.", 1))
        return issues

    def _gap_count(self, frame: pd.DataFrame) -> int:
        timestamps = frame["timestamp"].dropna()
        if len(timestamps) < 2:
            return 0
        return int((timestamps.diff().dt.total_seconds().div(86400) > self.max_gap_days).sum())

    def _components(self, frame: pd.DataFrame, issues: list[DataValidationIssue]) -> tuple[dict[str, float], int]:
        total = max(len(frame) * len(REQUIRED_OHLCV_COLUMNS), 1)
        nulls = int(frame.loc[:, list(REQUIRED_OHLCV_COLUMNS)].isna().sum().sum())
        duplicates = int(frame["timestamp"].duplicated().sum())
        chronological = float(frame["timestamp"].is_monotonic_increasing)
        prices = frame[["open", "high", "low", "close"]]
        invalid_ohlc = int(((frame["high"] < frame[["open", "low", "close"]].max(axis=1)) | (frame["low"] > frame[["open", "high", "close"]].min(axis=1))).sum())
        gaps = self._gap_count(frame)
        return {
            "completeness": max(0.0, 1 - nulls / total),
            "nan_rate": nulls / total,
            "duplicate_rate": duplicates / max(len(frame), 1),
            "chronological_consistency": chronological,
            "ohlc_validity": max(0.0, 1 - invalid_ohlc / max(len(frame), 1)),
            "gap_severity": gaps / max(len(frame) - 1, 1),
            "timezone_consistency": float(isinstance(frame["timestamp"].dtype, pd.DatetimeTZDtype)),
        }, gaps
