"""Structured, privacy-conscious logging helpers for local FinAgent work."""

from __future__ import annotations

import logging
import json
import re
from datetime import UTC, datetime
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Emit compact JSON logs suitable for local debugging and demos."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if getattr(record, "event", None) is None:
            match = re.match(r"event=([A-Z0-9_]+)", record.getMessage())
            if match:
                payload["event"] = match.group(1)
        for key in ("event", "request_id", "method", "path", "status_code", "duration_ms", "workflow", "artifact_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure a JSON logger once and return the FinAgent logger."""
    logger = logging.getLogger("finagent")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Record an event without serialising credentials, raw request bodies, or data rows."""

    safe_fields = {key: value for key, value in fields.items() if key not in {"authorization", "token", "password", "secret", "body"}}
    logger.log(level, event, extra={"event": event, **safe_fields})
