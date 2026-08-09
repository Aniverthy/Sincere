"""Structured-logging tests (§22).

Two guarantees, both learned the hard way:

* A log line must never crash the caller. `extra={"name": ...}` raises `KeyError` in the
  stdlib, and it took down application startup the first time it ran against a real Atlas
  cluster — the offending branch only executes when the vector index already exists.
* §22's redaction list is enforced by the pipeline, not by discipline at the call site.
"""

from __future__ import annotations

import json
import logging

import pytest

from sincere.shared.logging import (
    REDACTED,
    JsonFormatter,
    RedactionFilter,
    hash_user_id,
    install_reserved_key_guard,
)


@pytest.fixture(autouse=True)
def _guard() -> None:
    install_reserved_key_guard()


def emit(caplog: pytest.LogCaptureFixture, **extra: object) -> logging.LogRecord:
    logger = logging.getLogger("test.logging")
    with caplog.at_level(logging.INFO, logger="test.logging"):
        logger.info("event.happened", extra=extra)
    return caplog.records[-1]


class TestReservedKeyGuard:
    """A log line must never be able to take the process down."""

    @pytest.mark.parametrize(
        "key", ["name", "module", "message", "args", "filename", "lineno", "process", "asctime"]
    )
    def test_reserved_keys_do_not_raise(self, key: str, caplog: pytest.LogCaptureFixture) -> None:
        record = emit(caplog, **{key: "value"})
        assert record is not None

    def test_reserved_key_value_is_preserved_under_a_prefix(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Renamed, not dropped — the value still has to reach the log store."""
        record = emit(caplog, name="embedding_vector_index")
        assert record.ctx_name == "embedding_vector_index"

    def test_ordinary_keys_are_untouched(self, caplog: pytest.LogCaptureFixture) -> None:
        record = emit(caplog, region="8660145b7ffffff", count=3)
        assert record.region == "8660145b7ffffff"
        assert record.count == 3

    def test_guard_is_idempotent(self, caplog: pytest.LogCaptureFixture) -> None:
        """Installing twice must not double-prefix or recurse."""
        install_reserved_key_guard()
        install_reserved_key_guard()
        record = emit(caplog, name="x")
        assert record.ctx_name == "x"
        assert not hasattr(record, "ctx_ctx_name")


class TestRedaction:
    """§22: message bodies, vectors, OTPs, tokens and raw locations never reach the store."""

    @pytest.mark.parametrize(
        "key",
        ["body", "message_body", "vector", "embedding", "otp", "token", "refresh_token",
         "authorization", "password", "phone", "coordinates"],
    )
    def test_forbidden_keys_are_redacted(self, key: str) -> None:
        record = logging.LogRecord("t", logging.INFO, "f", 1, "msg", None, None)
        setattr(record, key, "secret-value")
        RedactionFilter().filter(record)
        assert getattr(record, key) == REDACTED

    def test_nested_values_are_redacted(self) -> None:
        record = logging.LogRecord("t", logging.INFO, "f", 1, "msg", None, None)
        record.payload = {"body": "hello there", "match_id": "m1"}
        RedactionFilter().filter(record)
        assert record.payload["body"] == REDACTED
        assert record.payload["match_id"] == "m1"

    def test_phone_hash_is_allowed_but_phone_is_not(self) -> None:
        record = logging.LogRecord("t", logging.INFO, "f", 1, "msg", None, None)
        record.phone = "+919876543210"
        record.phone_hash = "abc123"
        RedactionFilter().filter(record)
        assert record.phone == REDACTED
        assert record.phone_hash == "abc123"


class TestJsonFormat:
    def test_output_is_one_json_object(self) -> None:
        record = logging.LogRecord("sincere.test", logging.INFO, "f", 1, "event.name", None, None)
        record.region = "8660145b7ffffff"
        payload = json.loads(JsonFormatter().format(record))

        assert payload["event"] == "event.name"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "sincere.test"
        assert payload["region"] == "8660145b7ffffff"
        assert "timestamp" in payload

    def test_user_ids_are_hashed_for_correlation(self) -> None:
        """§22 correlates on a hashed user id — logs are personal data too."""
        hashed = hash_user_id("user-123")
        assert hashed is not None
        assert hashed != "user-123"
        assert len(hashed) == 16
        assert hash_user_id("user-123") == hashed
        assert hash_user_id(None) is None
