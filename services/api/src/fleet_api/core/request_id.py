from uuid import UUID, uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from fleet_api.core.structured_logging import request_id_context


class RequestIdMiddleware:
    """Attach a correlation ID to every request and response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_request_id = next(
            (value for key, value in scope.get("headers", []) if key == b"x-request-id"),
            None,
        )
        request_id = self._safe_request_id(raw_request_id)
        token = request_id_context.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_context.reset(token)

    @staticmethod
    def _safe_request_id(raw_request_id: bytes | None) -> str:
        if raw_request_id:
            try:
                return str(UUID(raw_request_id.decode("ascii")))
            except (ValueError, UnicodeDecodeError):
                return str(uuid4())
        return str(uuid4())
