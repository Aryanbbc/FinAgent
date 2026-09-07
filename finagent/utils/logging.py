"""Structured, privacy-conscious logging helpers for local FinAgent work."""

from __future__ import annotations

import logging
import json
import re
from datetime import UTC, datetime
from typing import Any


_SENSITIVE_FIELD = re.compile(r"(api[_-]?key|authorization|token|password|secret|cookie|database[_-]?url|credential)", re.IGNORECASE)
_URL_CREDENTIALS = re.compile(r"((?:postgres(?:ql)?|https?)://)[^\s/@:]+(?::[^\s/@]*)?@", re.IGNORECASE)
_QUERY_SECRET = re.compile(r"([?&](?:apikey|api_key|token|password|secret|authorization)=)[^&\s]+", re.IGNORECASE)
_BEARER_SECRET = re.compile(r"(bearer\s+)[^\s]+", re.IGNORECASE)


def redact(value: Any) -> Any:
    """Redact likely credentials recursively before an event can reach a log sink."""
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if _SENSITIVE_FIELD.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return type(value)(redact(item) for item in value)
    if not isinstance(value, str):
        return value
    cleaned = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", value)
    cleaned = _QUERY_SECRET.sub(r"\1[REDACTED]", cleaned)
    return _BEARER_SECRET.sub(r"\1[REDACTED]", cleaned)


class _JsonFormatter(logging.Formatter):
    """Emit compact JSON logs suitable for local debugging and demos."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if getattr(record, "event", None) is None:
            match = re.match(r"event=([A-Z0-9_]+)", record.getMessage())
            if match:
                payload["event"] = match.group(1)
        for key in ("event", "request_id", "method", "path", "status_code", "duration_ms", "workflow", "artifact_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = redact(value)
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

    safe_fields = {
        key: redact(value)
        for key, value in fields.items()
        if not _SENSITIVE_FIELD.search(key) and key not in {"body", "headers", "request_body"}
    }
    logger.log(level, event, extra={"event": event, **safe_fields})
