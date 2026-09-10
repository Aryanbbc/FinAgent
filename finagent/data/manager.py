"""Historical-data fetching, deterministic cache management, and registry persistence."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from finagent.data.market_provider import MarketDataProvider, MarketDataProviderError, ProviderRegistry
from finagent.data.models import DatasetVersion, MarketDataRequest, MissingDataPolicy
from finagent.data.quality import DataValidationPipeline
from finagent.data.registry import DatasetRegistry
from finagent.data.validator import DataValidationError


@dataclass(frozen=True)
class DatasetFetchResult:
    dataset: DatasetVersion
    cache_hit: bool
    requested_provider: str
    actual_provider: str
    fallback_used: bool
    attempts: tuple[dict[str, object], ...] = ()


class DatasetManager:
    """Coordinates providers, validation, cache revisions, and metadata without trading behavior."""

    def __init__(
        self,
        registry: DatasetRegistry,
        cache_root: str | Path,
        providers: ProviderRegistry | None = None,
        pipeline: DataValidationPipeline | None = None,
        *,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 0.25,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.registry = registry
        self.cache_root = Path(cache_root)
        self.providers = providers or ProviderRegistry()
        self.pipeline = pipeline or DataValidationPipeline()
        self.max_attempts = max(1, max_attempts)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self._sleep = sleep

    def fetch(self, provider_name: str, request: MarketDataRequest, policy: MissingDataPolicy = MissingDataPolicy.REJECT) -> DatasetFetchResult:
        candidates = self.providers.candidates(provider_name, request)
        # Validate before looking at the cache so invalid requests cannot reuse
        # a historical revision merely because its identifier happens to match.
        candidates[0].validate_request(request)
        dataset_id = self.registry.make_dataset_id(provider_name, request.symbol, request.interval)
        if not request.force_refresh:
            try:
                cached = self.registry.latest(dataset_id)
                if (
                    cached.validation.status.value != "invalid"
                    and (self.registry.has_ohlcv(cached.version_id) or Path(cached.cache_path).is_file())
                    and self._cached_covers(cached, request)
                ):
                    actual_provider = cached.metadata.actual_provider or cached.provider
                    return DatasetFetchResult(
                        cached,
                        True,
                        provider_name,
                        actual_provider,
                        provider_name == self.providers.auto_provider
                        and not self.providers.is_primary_auto_provider(actual_provider, request),
                    )
            except LookupError:
                pass
        raw, provider, attempts, fallback_used = self._fetch_from_candidates(provider_name, candidates, request)
        frame, validation = self.pipeline.prepare(raw, policy)
        if validation.status.value == "invalid":
            # ``warn_only`` may be useful to inspect a provider response in an
            # in-memory assessment, but an invalid series must never become a
            # selectable immutable research dataset.
            issues = "; ".join(issue.message for issue in validation.issues if issue.severity == "error")
            raise DataValidationError(issues or "Historical OHLCV validation failed")
        if frame.empty:
            raise MarketDataProviderError("EMPTY_RESULT", f"No usable rows returned for {request.symbol}.", provider=provider.provider_name)
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
        provider_metadata = provider.fetch_metadata(request)
        metadata = replace(
            provider_metadata,
            requested_provider=provider_name,
            actual_provider=provider.provider_name,
            provider_symbol=provider_metadata.provider_symbol or request.symbol,
            fetch_timestamp=datetime.now(UTC).isoformat(),
            requested_date_range={"start_date": request.start_date, "end_date": request.end_date},
            requested_interval=request.interval,
        )
        dataset = self.registry.save_version_with_ohlcv(
            dataset_id=dataset_id, provider=provider.provider_name, symbol=request.symbol, interval=request.interval,
            start_date=str(frame["timestamp"].iloc[0].date()), end_date=str(frame["timestamp"].iloc[-1].date()),
            row_count=len(frame), cache_path=cache_path, checksum=checksum, validation=validation, metadata=metadata,
            frame=frame,
            dataset_provider=provider_name,
        )
        # The CSV cache remains a local-development convenience.  The immutable
        # canonical rows make production datasets durable across Render restarts.
        actual_provider = dataset.metadata.actual_provider or dataset.provider
        return DatasetFetchResult(
            dataset,
            False,
            provider_name,
            actual_provider,
            provider_name == self.providers.auto_provider
            and not self.providers.is_primary_auto_provider(actual_provider, request),
            tuple(attempts),
        )

    def _fetch_from_candidates(
        self,
        requested_provider: str,
        candidates: tuple[MarketDataProvider, ...],
        request: MarketDataRequest,
    ) -> tuple[pd.DataFrame, MarketDataProvider, list[dict[str, object]], bool]:
        """Fetch from the selected provider(s), retrying only transient errors.

        ``auto`` has a fixed public-provider order.  A fallback is considered
        only after the current provider reports a retryable failure, so a bad
        symbol or malformed request cannot be silently masked by another feed.
        """
        attempts: list[dict[str, object]] = []
        errors: list[MarketDataProviderError] = []
        for index, candidate in enumerate(candidates):
            provider = candidate
            try:
                raw = self._fetch_with_retry(provider, request, attempts)
                return raw, provider, attempts, index > 0
            except MarketDataProviderError as error:
                error.provider = error.provider or provider.provider_name
                errors.append(error)
                if requested_provider != self.providers.auto_provider or not error.retryable or index == len(candidates) - 1:
                    if requested_provider == self.providers.auto_provider and len(errors) > 1:
                        raise self._fallback_failure(errors) from error
                    error.fallback_used = index > 0
                    raise
        # ``ProviderRegistry.candidates`` guarantees a non-empty sequence.
        raise self._fallback_failure(errors)

    def _fetch_with_retry(self, provider: MarketDataProvider, request: MarketDataRequest, attempts: list[dict[str, object]]) -> pd.DataFrame:
        for attempt_number in range(1, self.max_attempts + 1):
            try:
                return provider.fetch_ohlcv(request)
            except MarketDataProviderError as error:
                error.provider = error.provider or provider.provider_name
                attempts.append({
                    "provider": error.provider,
                    "attempt": attempt_number,
                    "status": error.status,
                    "reason": error.reason,
                    "retryable": error.retryable,
                })
                if not error.retryable or attempt_number == self.max_attempts:
                    raise
                self._sleep(self.retry_backoff_seconds * (2 ** (attempt_number - 1)))
        raise AssertionError("unreachable retry loop")

    @staticmethod
    def _fallback_failure(errors: list[MarketDataProviderError]) -> MarketDataProviderError:
        final = errors[-1]
        reason = "; ".join(f"{error.provider}: {error.reason}" for error in errors)
        return MarketDataProviderError(
            "ALL_PROVIDERS_FAILED",
            "All configured public historical-data providers failed.",
            provider="auto",
            status=final.status,
            reason=reason,
            retryable=any(error.retryable for error in errors),
            fallback_used=True,
        )

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
        """Return true only when an immutable revision covers every requested date.

        A former three-day boundary tolerance could reuse a Friday-ending cache
        for a Monday request (or the reverse at the leading edge), silently
        omitting a trading session.  Exact coverage favours reproducibility
        over an unnecessary provider request on a non-trading day.
        """
        try:
            requested_start, requested_end = date.fromisoformat(request.start_date), date.fromisoformat(request.end_date)
            cached_start, cached_end = date.fromisoformat(dataset.start_date), date.fromisoformat(dataset.end_date)
        except ValueError:
            return False
        return cached_start <= requested_start and cached_end >= requested_end
