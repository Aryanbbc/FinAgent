"""Historical-data fetching, deterministic cache management, and registry persistence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from finagent.data.market_provider import MarketDataProviderError, ProviderRegistry
from finagent.data.models import DatasetVersion, MarketDataRequest, MissingDataPolicy
from finagent.data.quality import DataValidationPipeline
from finagent.data.registry import DatasetRegistry


@dataclass(frozen=True)
class DatasetFetchResult:
    dataset: DatasetVersion
    cache_hit: bool


class DatasetManager:
    """Coordinates providers, validation, cache revisions, and metadata without trading behavior."""

    def __init__(self, registry: DatasetRegistry, cache_root: str | Path, providers: ProviderRegistry | None = None, pipeline: DataValidationPipeline | None = None) -> None:
        self.registry = registry
        self.cache_root = Path(cache_root)
        self.providers = providers or ProviderRegistry()
        self.pipeline = pipeline or DataValidationPipeline()

    def fetch(self, provider_name: str, request: MarketDataRequest, policy: MissingDataPolicy = MissingDataPolicy.REJECT) -> DatasetFetchResult:
        provider = self.providers.get(provider_name)
        provider.validate_request(request)
        dataset_id = self.registry.make_dataset_id(provider_name, request.symbol, request.interval)
        if not request.force_refresh:
            try:
                cached = self.registry.latest(dataset_id)
                if (
                    cached.validation.status.value != "invalid"
                    and (self.registry.has_ohlcv(cached.version_id) or Path(cached.cache_path).is_file())
                    and self._cached_covers(cached, request)
                ):
                    return DatasetFetchResult(cached, True)
            except LookupError:
                pass
        raw = provider.fetch_ohlcv(request)
        frame, validation = self.pipeline.prepare(raw, policy)
        if frame.empty:
            raise MarketDataProviderError("EMPTY_RESULT", f"No usable rows returned for {request.symbol}.")
        checksum = self._checksum(frame)
        version_number = self.registry.next_version_number(dataset_id)
        cache_path = self._cache_path(provider_name, request.symbol, request.interval, dataset_id, version_number)
        previous: DatasetVersion | None = None
        try:
            previous = self.registry.latest(dataset_id)
        except LookupError:
            pass
        if previous is None or previous.checksum != checksum:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_suffix(".tmp")
            frame.to_csv(temporary, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")
            temporary.replace(cache_path)
        else:
            cache_path = Path(previous.cache_path)
        metadata = provider.fetch_metadata(request)
        dataset = self.registry.save_version(
            dataset_id=dataset_id, provider=provider_name, symbol=request.symbol, interval=request.interval,
            start_date=str(frame["timestamp"].iloc[0].date()), end_date=str(frame["timestamp"].iloc[-1].date()),
            row_count=len(frame), cache_path=cache_path, checksum=checksum, validation=validation, metadata=metadata,
        )
        # The CSV cache remains a local-development convenience.  The immutable
        # canonical rows make production datasets durable across Render restarts.
        self.registry.store_ohlcv(dataset.version_id, frame)
        return DatasetFetchResult(dataset, False)

    def validate(self, dataset_id: str, policy: MissingDataPolicy = MissingDataPolicy.REJECT) -> DatasetVersion:
        dataset = self.registry.latest(dataset_id)
        frame = (
            self.registry.load_ohlcv(dataset.version_id)
            if self.registry.has_ohlcv(dataset.version_id)
            else pd.read_csv(dataset.cache_path)
        )
        _, validation = self.pipeline.prepare(frame, policy)
        return self.registry.save_version(
            dataset_id=dataset.dataset_id, provider=dataset.provider, symbol=dataset.symbol, interval=dataset.interval,
            start_date=dataset.start_date, end_date=dataset.end_date, row_count=dataset.row_count, cache_path=dataset.cache_path,
            checksum=dataset.checksum, validation=validation, metadata=dataset.metadata,
        )

    def _cache_path(self, provider: str, symbol: str, interval: str, dataset_id: str, version_number: int) -> Path:
        safe_symbol = "".join(character if character.isalnum() or character in "._-" else "_" for character in symbol.upper())
        return self.cache_root / provider / safe_symbol / interval / dataset_id / f"v{version_number:03d}.csv"

    @staticmethod
    def _checksum(frame: pd.DataFrame) -> str:
        payload = frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%S%z", float_format="%.10g").encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _cached_covers(dataset: DatasetVersion, request: MarketDataRequest) -> bool:
        """Avoid duplicate downloads while allowing a small non-trading-day boundary tolerance."""
        try:
            requested_start, requested_end = date.fromisoformat(request.start_date), date.fromisoformat(request.end_date)
            cached_start, cached_end = date.fromisoformat(dataset.start_date), date.fromisoformat(dataset.end_date)
        except ValueError:
            return False
        tolerance = timedelta(days=3)
        return cached_start <= requested_start + tolerance and cached_end >= requested_end - tolerance
