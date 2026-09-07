"""Small, dependency-free controls for the public FinAgent API surface.

This module intentionally implements only a single shared administrator key and
per-process request limits.  It is not a user-account system and is kept out of
the deterministic research engine.
"""

from __future__ import annotations

from collections import OrderedDict, deque
import hmac
from threading import Lock
import time
from typing import Deque

from fastapi import Header, HTTPException, Request, status

from finagent.api.settings import Settings
from finagent.utils.logging import log_event


ADMIN_KEY_HEADER = "X-FinAgent-Admin-Key"


class BoundedRateLimiter:
    """Fixed-window limiter with a hard cap on retained client state.

    Render can run more than one worker/instance, so this intentionally limits
    one process rather than claiming globally distributed enforcement.  The
    bounded LRU state avoids turning an attacker-controlled client key into an
    unbounded in-memory collection.
    """

    def __init__(self, *, limit: int, window_seconds: int, max_clients: int = 1_024) -> None:
        if limit < 1 or window_seconds < 1 or max_clients < 1:
            raise ValueError("rate-limit values must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._requests: OrderedDict[str, Deque[float]] = OrderedDict()
        self._lock = Lock()

    def check(self, key: str, *, now: float | None = None) -> int | None:
        """Record an allowed request, or return the non-zero retry delay."""
        current = time.monotonic() if now is None else now
        with self._lock:
            timestamps = self._requests.get(key)
            if timestamps is None:
                if len(self._requests) >= self.max_clients:
                    self._requests.popitem(last=False)
                timestamps = deque()
                self._requests[key] = timestamps
            else:
                self._requests.move_to_end(key)
            cutoff = current - self.window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self.limit:
                return max(1, int(self.window_seconds - (current - timestamps[0])) + 1)
            timestamps.append(current)
            return None


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _logger(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.logger


def _client_key(request: Request) -> str:
    """Use the direct peer address; forwarded headers are spoofable by default."""
    return request.client.host if request.client else "unknown"


def audit_admin_action(request: Request, event: str) -> None:
    """Emit a credential-free audit event for an authorized privileged action."""
    log_event(
        _logger(request),
        event,
        path=request.url.path,
        method=request.method,
        request_id=getattr(request.state, "request_id", None),
    )


async def require_admin(
    request: Request,
    supplied_key: str | None = Header(default=None, alias=ADMIN_KEY_HEADER),
) -> None:
    """Require the configured backend-only key for state-changing API routes."""
    settings = _settings(request)
    if settings.admin_auth_disabled:
        return
    expected_key = settings.admin_api_key
    valid = bool(expected_key and supplied_key and hmac.compare_digest(expected_key, supplied_key))
    if valid:
        return
    log_event(
        _logger(request),
        "AUTH_FAILURE",
        path=request.url.path,
        method=request.method,
        request_id=getattr(request.state, "request_id", None),
        reason="missing_or_invalid_admin_key",
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="An administrator key is required for this action.",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def require_mutation_rate_limit(request: Request) -> None:
    """Enforce the bounded per-instance mutation limit after authentication."""
    limiter: BoundedRateLimiter = request.app.state.mutation_limiter
    retry_after = limiter.check(_client_key(request))
    if retry_after is None:
        return
    log_event(
        _logger(request),
        "RATE_LIMIT_TRIGGERED",
        path=request.url.path,
        method=request.method,
        request_id=getattr(request.state, "request_id", None),
        retry_after=retry_after,
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many privileged research requests. Retry after the indicated delay.",
        headers={"Retry-After": str(retry_after)},
    )


async def require_report_rate_limit(request: Request) -> None:
    """Bound public report materialization without turning report reads into auth."""
    limiter: BoundedRateLimiter = request.app.state.report_limiter
    retry_after = limiter.check(_client_key(request))
    if retry_after is None:
        return
    log_event(
        _logger(request),
        "RATE_LIMIT_TRIGGERED",
        path=request.url.path,
        method=request.method,
        request_id=getattr(request.state, "request_id", None),
        retry_after=retry_after,
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many report requests. Retry after the indicated delay.",
        headers={"Retry-After": str(retry_after), "X-FinAgent-Rate-Limit-Scope": "reports"},
    )
