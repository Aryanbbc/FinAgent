"""Structured logging helpers for local experiment runs."""

from __future__ import annotations

import logging


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure a compact structured logger once and return the FinAgent logger."""
    logger = logging.getLogger("finagent")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger
