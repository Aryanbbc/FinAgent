"""Environment-backed settings for local development and explicit public deployment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


_LOCAL_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")
_VALID_ENVIRONMENTS = {"development", "test", "production"}


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


@dataclass(frozen=True)
class Settings:
    """Runtime locations, platform binding, and explicit CORS origins for FinAgent."""

    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///data/finagent.db"))
    environment: str = field(default_factory=_environment)
    host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    port: int = field(default_factory=_port)
    cors_origins: tuple[str, ...] = field(default_factory=lambda: _configured_origins(_environment()))
    data_cache_directory: Path | None = None
    reports_directory: Path | None = None

    def __post_init__(self) -> None:
        if self.environment not in _VALID_ENVIRONMENTS:
            raise ValueError("FINAGENT_ENV must be development, test, or production")
        if self.host == "*":
            raise ValueError("API_HOST must be an explicit host address")
        if "*" in self.cors_origins:
            raise ValueError("Wildcard CORS origins are not permitted")
        if self.environment == "production" and not any(origin not in _LOCAL_CORS_ORIGINS for origin in self.cors_origins):
            raise ValueError("A deployed FRONTEND_ORIGIN is required in production")
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
