"""
In-memory sliding-window rate limiter for the AI triage endpoint.

Limit: 10 POST /triage/ requests per user per 60-second window.

IMPORTANT — production note
---------------------------
This implementation tracks request counts in a process-local dict.  It works
correctly for a single-process deployment (e.g., one Uvicorn worker).  For
multi-instance or multi-worker deployments, replace ``_windows`` with a
Redis-backed counter (e.g., ``slowapi`` + Redis) to share state across
processes.
"""
from __future__ import annotations

import collections
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_WINDOW_SECONDS: int = 60
_MAX_REQUESTS: int = 10
_TRIAGE_PATH: str = "/triage"

# bearer-token → deque of monotonic timestamps for the sliding window
_windows: dict[str, deque[float]] = {}


def _is_rate_limited(key: str) -> tuple[bool, int]:
    """Sliding-window rate-limit check.

    Returns ``(is_limited, retry_after_seconds)``.  The window is maintained
    per opaque bearer-token string so that no JWT decoding (and no DB look-up)
    is required in middleware.
    """
    now = time.monotonic()
    dq = _windows.setdefault(key, deque())

    # Evict timestamps that have fallen outside the current window
    cutoff = now - _WINDOW_SECONDS
    while dq and dq[0] <= cutoff:
        dq.popleft()

    if len(dq) >= _MAX_REQUESTS:
        retry_after = int(_WINDOW_SECONDS - (now - dq[0])) + 1
        return True, retry_after

    dq.append(now)
    return False, 0


class TriageRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply per-user rate limiting to ``POST /triage/`` requests.

    Unauthenticated requests (no ``Authorization`` header) are passed through
    unchanged — the authentication layer handles those with HTTP 401.
    """

    async def dispatch(self, request: Request, call_next):
        if (
            request.method == "POST"
            and request.url.path.rstrip("/") == _TRIAGE_PATH
        ):
            auth = request.headers.get("authorization", "")
            token = auth.removeprefix("Bearer ").strip()

            if token:
                limited, retry_after = _is_rate_limited(token)
                if limited:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": (
                                "Rate limit exceeded. "
                                "Maximum 10 triage requests per minute."
                            )
                        },
                        headers={"Retry-After": str(retry_after)},
                    )

        return await call_next(request)
