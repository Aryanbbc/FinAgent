"""Environment-backed settings for local development and explicit public deployment."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


_LOCAL_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")
_VALID_ENVIRONMENTS = {"development", "test", "production"}
_LIVE_INTERVALS = {"1min", "5min", "15min"}


def _environment() -> str:
    value = os.getenv("FINAGENT_ENV", "development").strip().lower()
    if value not in _VALID_ENVIRONMENTS:
        raise ValueError("FINAGENT_ENV must be development, test, or production")
    return value


def _port() -> int:
    """Prefer platform-standard PORT while retaining API_PORT for local compatibility."""
    value = os.getenv("PORT") or os.getenv("API_PORT", "8000")
    try:
        port = int(value)
    except ValueError as error:
        raise ValueError("PORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    return port


def _configured_origins(environment: str) -> tuple[str, ...]:
    """Return explicit development and configured deployment origins; never a wildcard."""
    raw = os.getenv("FRONTEND_ORIGIN", "").strip()
    supplied = tuple(item.strip().rstrip("/") for item in raw.split(",") if item.strip())
    if environment == "production" and not supplied:
        raise ValueError("FRONTEND_ORIGIN is required when FINAGENT_ENV=production")
    for origin in supplied:
        parsed = urlparse(origin)
        if origin == "*" or parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("FRONTEND_ORIGIN must contain one or more exact http(s) origins without paths")
    return tuple(dict.fromkeys((*_LOCAL_CORS_ORIGINS, *supplied)))


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _positive_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _live_symbols() -> tuple[str, ...]:
    default = os.getenv("LIVE_DEFAULT_SYMBOL", "AAPL")
    raw = os.getenv("LIVE_SYMBOLS", default)
    symbols = tuple(item.strip().upper() for item in raw.split(",") if item.strip())
    if not symbols:
        raise ValueError("LIVE_DEFAULT_SYMBOL or LIVE_SYMBOLS must contain at least one symbol")
    if len(symbols) > 10:
        raise ValueError("LIVE_SYMBOLS may contain at most 10 configured symbols")
    if any(not re.fullmatch(r"[A-Z0-9._^=-]{1,32}", symbol) for symbol in symbols):
        raise ValueError("LIVE_SYMBOLS must contain valid symbols without whitespace")
    return tuple(dict.fromkeys(symbols))


def _admin_api_key() -> str | None:
    """Read the administrator key only from the backend process environment."""
    value = os.getenv("FINAGENT_ADMIN_API_KEY", "").strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    """Runtime locations, platform binding, and explicit CORS origins for FinAgent."""

    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///data/finagent.db"))
    environment: str = field(default_factory=_environment)
    # Render must bind the container service interface explicitly.
    host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))  # nosec B104
    port: int = field(default_factory=_port)
    cors_origins: tuple[str, ...] = field(default_factory=lambda: _configured_origins(_environment()))
    data_cache_directory: Path | None = None
    reports_directory: Path | None = None
    # This value is deliberately excluded from the dataclass repr so a Settings
    # object cannot accidentally reveal the deployment credential in logs.
    admin_api_key: str | None = field(default_factory=_admin_api_key, repr=False)
    admin_auth_disabled: bool = field(default_factory=lambda: _boolean("FINAGENT_DISABLE_ADMIN_AUTH", False))
    mutation_rate_limit: int = field(default_factory=lambda: _positive_int("FINAGENT_MUTATION_RATE_LIMIT", 5, minimum=1, maximum=20))
    mutation_rate_window_seconds: int = field(default_factory=lambda: _positive_int("FINAGENT_MUTATION_RATE_WINDOW_SECONDS", 300, minimum=30, maximum=3_600))
    # Live monitoring is an explicit non-executing opt-in.  Credentials are
    # intentionally not represented here and remain provider-local env values.
    live_market_enabled: bool = field(default_factory=lambda: _boolean("LIVE_MARKET_ENABLED", False))
    live_trading_enabled: bool = field(default_factory=lambda: _boolean("LIVE_TRADING_ENABLED", False))
    live_default_symbol: str = field(default_factory=lambda: os.getenv("LIVE_DEFAULT_SYMBOL", "AAPL").strip().upper())
    live_symbols: tuple[str, ...] = field(default_factory=_live_symbols)
    live_interval: str = field(default_factory=lambda: os.getenv("LIVE_INTERVAL", "1min").strip())
    live_buffer_size: int = field(default_factory=lambda: _positive_int("LIVE_BUFFER_SIZE", 300, minimum=50, maximum=5_000))
    live_poll_seconds: int = field(default_factory=lambda: _positive_int("LIVE_POLL_SECONDS", 60, minimum=15, maximum=3_600))
    live_retention: int = field(default_factory=lambda: _positive_int("LIVE_RETENTION", 500, minimum=50, maximum=10_000))
    live_max_backoff_seconds: int = field(default_factory=lambda: _positive_int("LIVE_MAX_BACKOFF_SECONDS", 900, minimum=60, maximum=86_400))

    def __post_init__(self) -> None:
        if self.environment not in _VALID_ENVIRONMENTS:
            raise ValueError("FINAGENT_ENV must be development, test, or production")
        if self.host == "*":
            raise ValueError("API_HOST must be an explicit host address")
        if "*" in self.cors_origins:
            raise ValueError("Wildcard CORS origins are not permitted")
        if self.environment == "production" and not any(origin not in _LOCAL_CORS_ORIGINS for origin in self.cors_origins):
            raise ValueError("A deployed FRONTEND_ORIGIN is required in production")
        if self.admin_auth_disabled and self.environment != "development":
            raise ValueError("FINAGENT_DISABLE_ADMIN_AUTH is permitted only when FINAGENT_ENV=development")
        if self.environment == "production" and not self.admin_api_key:
            raise ValueError("FINAGENT_ADMIN_API_KEY is required when FINAGENT_ENV=production")
        if not self.live_default_symbol or any(character.isspace() for character in self.live_default_symbol):
            raise ValueError("LIVE_DEFAULT_SYMBOL must be a non-empty symbol without whitespace")
        if self.live_interval not in _LIVE_INTERVALS:
            choices = ", ".join(sorted(_LIVE_INTERVALS))
            raise ValueError(f"LIVE_INTERVAL must be one of: {choices}")
        if self.live_default_symbol not in self.live_symbols:
            raise ValueError("LIVE_DEFAULT_SYMBOL must be included in LIVE_SYMBOLS")
        if self.live_trading_enabled:
            raise ValueError("LIVE_TRADING_ENABLED must remain false; FinAgent has no execution path")
        normalized_url = self.database_url.lower()
        if not (
            normalized_url.startswith("sqlite://")
            or normalized_url.startswith("postgresql://")
            or normalized_url.startswith("postgres://")
            or "://" not in self.database_url
        ):
            raise ValueError("DATABASE_URL must use sqlite://, postgresql://, or postgres://")

    @property
    def database_backend(self) -> str:
        value = self.database_url.lower()
        return "postgresql" if value.startswith(("postgresql://", "postgres://")) else "sqlite"

    @property
    def database_path(self) -> Path:
        """Resolve a local SQLite path; PostgreSQL does not expose a filesystem path."""
        if self.database_backend != "sqlite":
            raise ValueError("database_path is only available when DATABASE_URL selects SQLite")
        prefix = "sqlite:///"
        value = self.database_url
        if value.startswith(prefix):
            value = value[len(prefix) :]
        path = Path(value)
        return path if path.is_absolute() else self.project_root / path

    @property
    def data_cache_path(self) -> Path:
        if self.data_cache_directory is not None:
            return self.data_cache_directory
        value = os.getenv("DATA_CACHE_PATH", "data/cache")
        path = Path(value)
        return path if path.is_absolute() else self.project_root / path

    @property
    def reports_path(self) -> Path:
        if self.reports_directory is not None:
            return self.reports_directory
        value = os.getenv("REPORTS_PATH", "reports")
        path = Path(value)
        return path if path.is_absolute() else self.project_root / path
