import io
import json
import logging
import sys

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.exc import StatementError

from fleet_api.core.config import Settings
from fleet_api.core.structured_logging import (
    JsonFormatter,
    configure_logging,
    request_id_context,
)
from fleet_api.db.session import engine
from fleet_api.main import create_app

SENSITIVE_VALUES = (
    "FAKE_ACCESS_TOKEN_MUST_NOT_BE_LOGGED",
    "FAKE_PIN_MUST_NOT_BE_LOGGED",
    "FAKE_ACTIVATION_MUST_NOT_BE_LOGGED",
    "postgresql://fake-user:FAKE_DB_PASSWORD@invalid.example/fleet",
)


def _raise_sensitive_database_error() -> None:
    token, pin, activation, database_url = SENSITIVE_VALUES
    try:
        raise ValueError(f"activation={activation}")
    except ValueError as cause:
        raise StatementError(
            f"token={token}",
            "INSERT INTO secret_test (pin) VALUES (:pin)",
            {"pin": pin},
            RuntimeError(database_url),
        ) from cause


def test_exception_metadata_omits_messages_parameters_source_and_locals() -> None:
    try:
        _raise_sensitive_database_error()
    except StatementError:
        record = logging.LogRecord(
            "fleet_api.test", logging.ERROR, __file__, 1, "operation_failed", (), sys.exc_info()
        )
        # A previous formatter may have cached unsafe exception/stack text.
        record.exc_text = " ".join(SENSITIVE_VALUES)
        record.stack_info = " ".join(SENSITIVE_VALUES)
    serialized = JsonFormatter().format(record)
    payload = json.loads(serialized)

    assert payload["message"] == "operation_failed"
    assert payload["exception"]["type"] == "sqlalchemy.exc.StatementError"
    assert payload["exception"]["frames"][-1]["function"] == "_raise_sensitive_database_error"
    for frame in payload["exception"]["frames"]:
        assert set(frame) == {"file", "function", "line"}
        assert frame["file"] == "test_structured_logging.py"
        assert isinstance(frame["line"], int)
    assert "INSERT INTO" not in serialized
    assert "ValueError" not in serialized
    for value in SENSITIVE_VALUES:
        assert value not in serialized


def test_regular_log_event_retains_request_correlation() -> None:
    context_token = request_id_context.set("12345678-1234-5678-1234-567812345678")
    try:
        record = logging.LogRecord(
            "fleet_api.test", logging.INFO, __file__, 1, "request_completed", (), None
        )
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_context.reset(context_token)

    assert payload["message"] == "request_completed"
    assert payload["request_id"] == "12345678-1234-5678-1234-567812345678"
    assert "exception" not in payload


def test_unhandled_request_does_not_log_or_return_database_secrets(
    monkeypatch: MonkeyPatch,
) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.setLevel(logging.ERROR)
    application_logger = logging.getLogger("fleet_api.main")
    monkeypatch.setattr(application_logger, "handlers", [handler])
    monkeypatch.setattr(application_logger, "propagate", False)
    application = create_app(Settings(environment="test"))

    @application.get("/test-unhandled")
    async def failing_endpoint() -> None:
        _raise_sensitive_database_error()

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/test-unhandled")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    payload = json.loads(stream.getvalue())
    assert payload["message"] == "unhandled_request_error"
    assert payload["exception"]["type"] == "sqlalchemy.exc.StatementError"
    for value in SENSITIVE_VALUES:
        assert value not in stream.getvalue()
        assert value not in response.text


def test_uvicorn_errors_use_the_same_safe_exception_formatter(monkeypatch: MonkeyPatch) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.WARNING)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        server_logger = logging.getLogger(name)
        monkeypatch.setattr(server_logger, "handlers", [logging.NullHandler()])
        monkeypatch.setattr(server_logger, "propagate", False)
        monkeypatch.setattr(server_logger, "level", logging.INFO)

    configure_logging("INFO")
    try:
        _raise_sensitive_database_error()
    except StatementError:
        logging.getLogger("uvicorn.error").exception("Exception in ASGI application")

    payload = json.loads(stream.getvalue())
    assert payload["exception"]["type"] == "sqlalchemy.exc.StatementError"
    for value in SENSITIVE_VALUES:
        assert value not in stream.getvalue()


def test_application_database_engine_hides_bound_parameters() -> None:
    assert engine.hide_parameters is True
