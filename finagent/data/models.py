"""Typed, provider-neutral records for FinAgent V0.8 historical datasets."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MissingDataPolicy(str, Enum):
    """Explicit handling for incomplete historical observations."""

    REJECT = "reject"
    FORWARD_FILL = "forward_fill"
    DROP = "drop"
    WARN_ONLY = "warn_only"


class ValidationStatus(str, Enum):
    VALID = "valid"
    WARNING = "warning"
    INVALID = "invalid"


@dataclass(frozen=True)
class MarketDataRequest:
    """A bounded request for one historical OHLCV series."""

    symbol: str
    start_date: str
    end_date: str
    interval: str = "1d"
    force_refresh: bool = False
    source_path: str | None = None
    asset_class: str = "equity"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "interval": self.interval,
            "force_refresh": self.force_refresh,
            "source_path": self.source_path,
            "asset_class": self.asset_class,
        }


@dataclass(frozen=True)
class AssetMetadata:
    symbol: str
    name: str | None = None
    exchange: str | None = None
    currency: str | None = None
    asset_class: str = "unknown"
    timezone: str | None = "UTC"
    adjustment_mode: str = "unknown"
    # Fetch provenance is stored with every immutable dataset revision.  These
    # optional fields keep older V0.8 records readable while making an
    # automatic provider fallback transparent to research consumers.
    requested_provider: str | None = None
    actual_provider: str | None = None
    provider_symbol: str | None = None
    fetch_timestamp: str | None = None
    requested_date_range: dict[str, str] | None = None
    requested_interval: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "exchange": self.exchange,
            "currency": self.currency,
            "asset_class": self.asset_class,
            "timezone": self.timezone,
            "adjustment_mode": self.adjustment_mode,
            "requested_provider": self.requested_provider,
            "actual_provider": self.actual_provider,
            "provider_symbol": self.provider_symbol,
            "fetch_timestamp": self.fetch_timestamp,
            "requested_date_range": self.requested_date_range,
            "requested_interval": self.requested_interval,
        }


@dataclass(frozen=True)
class DataValidationIssue:
    code: str
    severity: str
    message: str
    count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "message": self.message, "count": self.count}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DataValidationIssue":
        return cls(str(data["code"]), str(data["severity"]), str(data["message"]), int(data.get("count", 0)))


@dataclass(frozen=True)
class DataQualityScore:
    score: float
    components: dict[str, float]
    suspicious_gap_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "components": self.components, "suspicious_gap_count": self.suspicious_gap_count}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DataQualityScore":
        return cls(float(data["score"]), {str(key): float(value) for key, value in data.get("components", {}).items()}, int(data.get("suspicious_gap_count", 0)))


@dataclass(frozen=True)
class DatasetValidationResult:
    status: ValidationStatus
    issues: tuple[DataValidationIssue, ...]
    quality: DataQualityScore
    policy: MissingDataPolicy

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "issues": [item.to_dict() for item in self.issues],
            "quality": self.quality.to_dict(),
            "policy": self.policy.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetValidationResult":
        return cls(
            ValidationStatus(str(data["status"])),
            tuple(DataValidationIssue.from_dict(dict(item)) for item in data.get("issues", [])),
            DataQualityScore.from_dict(dict(data["quality"])),
            MissingDataPolicy(str(data.get("policy", MissingDataPolicy.REJECT.value))),
        )


@dataclass(frozen=True)
class DatasetVersion:
    dataset_id: str
    version_id: str
    version_number: int
    provider: str
    symbol: str
    asset_class: str
    exchange: str | None
    interval: str
    start_date: str
    end_date: str
    row_count: int
    cache_path: str
    checksum: str
    created_at: str
    last_refreshed_at: str
    validation: DatasetValidationResult
    metadata: AssetMetadata

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "version_id": self.version_id,
            "version_number": self.version_number,
            "provider": self.provider,
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "exchange": self.exchange,
            "interval": self.interval,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "row_count": self.row_count,
            "cache_path": self.cache_path,
            "checksum": self.checksum,
            "created_at": self.created_at,
            "last_refreshed_at": self.last_refreshed_at,
            "validation": self.validation.to_dict(),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class DatasetCollection:
    collection_id: str
    name: str
    description: str | None
    members: tuple[dict[str, str], ...] = field(default_factory=tuple)
    created_at: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "collection_id": self.collection_id,
            "name": self.name,
            "description": self.description,
            "members": [dict(item) for item in self.members],
            "created_at": self.created_at,
            "warnings": list(self.warnings),
        }
