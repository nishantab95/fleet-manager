import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    """Small JSON formatter that avoids serializing request bodies or PII."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            exception_type, _, traceback = record.exc_info
            if exception_type is not None:
                # Exception messages, chained exceptions, source lines, and
                # frame locals can contain credentials or database parameters.
                # Read code locations directly without formatting the error.
                frames: list[dict[str, str | int]] = []
                while traceback is not None:
                    code = traceback.tb_frame.f_code
                    frames.append(
                        {
                            "file": Path(code.co_filename).name,
                            "function": code.co_name,
                            "line": traceback.tb_lineno,
                        }
                    )
                    traceback = traceback.tb_next
                payload["exception"] = {
                    "type": f"{exception_type.__module__}.{exception_type.__name__}",
                    "frames": frames[-32:],
                }
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Uvicorn installs its own non-propagating handlers before app startup.
    # ServerErrorMiddleware re-raises handled failures to the ASGI server, so
    # those handlers must use this same safe exception policy as application logs.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.propagate = True
        server_logger.setLevel(logging.NOTSET)
