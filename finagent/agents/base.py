"""Reusable base interface and structured logging for deterministic agents."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Generic, TypeVar


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class BaseAgent(ABC, Generic[InputT, OutputT]):
    """A small, stateless agent contract with auditable structured output logging."""

    name: str
    version = "0.3"

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("finagent.agents")

    def run(self, agent_input: InputT) -> OutputT:
        """Generate output and log it as a structured, machine-readable event."""
        output = self.analyze(agent_input)
        serializer = getattr(output, "to_dict", None)
        payload = serializer() if callable(serializer) else {"output_type": type(output).__name__}
        self.logger.debug(
            "event=AGENT_DECISION agent=%s version=%s payload=%s",
            self.name,
            self.version,
            json.dumps(payload, default=str, sort_keys=True),
        )
        return output

    @abstractmethod
    def analyze(self, agent_input: InputT) -> OutputT:
        """Return typed deterministic output for one causal market observation."""
