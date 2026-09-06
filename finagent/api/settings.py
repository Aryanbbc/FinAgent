"""Environment-backed settings for the local-only V0.8 API."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime locations and network binding for the local research API."""

    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///data/finagent.db"))
    host: str = field(default_factory=lambda: os.getenv("API_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8000")))
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    data_cache_directory: Path | None = None

    @property
    def database_path(self) -> Path:
        """Resolve a SQLite URL or a local path without accepting remote databases."""
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
