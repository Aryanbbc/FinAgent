"""Historical market-data interfaces, providers, validation, cache, and registry."""

from finagent.data.loader import CSVDataLoader
from finagent.data.manager import DatasetManager
from finagent.data.market_provider import LocalCSVProvider, MarketDataProvider, MarketDataProviderError, ProviderRegistry, YahooFinanceProvider
from finagent.data.models import MarketDataRequest, MissingDataPolicy
from finagent.data.registry import DatasetNotFoundError, DatasetRegistry
from finagent.data.validator import DataValidationError, OHLCVValidator

__all__ = [
    "CSVDataLoader", "DataValidationError", "DatasetManager", "DatasetNotFoundError", "DatasetRegistry",
    "LocalCSVProvider", "MarketDataProvider", "MarketDataProviderError", "MarketDataRequest", "MissingDataPolicy",
    "OHLCVValidator", "ProviderRegistry", "YahooFinanceProvider",
]
