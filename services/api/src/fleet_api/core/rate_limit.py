from __future__ import annotations

import asyncio
import ipaddress
import time
from collections import deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Bound public requests per client for the single-process VPS deployment."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        requests_per_minute: int,
        auth_requests_per_minute: int,
        max_clients: int,
    ) -> None:
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.auth_requests_per_minute = auth_requests_per_minute
        self.max_clients = max_clients
        self._requests: dict[tuple[str, str], deque[float]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _client_key(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        candidate = forwarded or (request.client.host if request.client else "unknown")
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            return "unknown"

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in {"/health", "/ready"}:
            return await call_next(request)

        auth_request = request.url.path.startswith("/api/v1/auth/")
        limit = self.auth_requests_per_minute if auth_request else self.requests_per_minute
        if limit <= 0:
            return await call_next(request)

        now = time.monotonic()
        boundary = now - 60.0
        bucket_name = "auth" if auth_request else "general"
        key = (bucket_name, self._client_key(request))
        async with self._lock:
            bucket = self._requests.get(key)
            if bucket is None:
                if len(self._requests) >= self.max_clients:
                    self._requests.pop(next(iter(self._requests)))
                bucket = deque()
                self._requests[key] = bucket
            while bucket and bucket[0] <= boundary:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(60 - (now - bucket[0])))
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many requests. Please try again later."},
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)
        return await call_next(request)
