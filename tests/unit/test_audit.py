import logging
import sys

import pytest

from app.core.audit import audit_logger, configure_logging


@pytest.fixture(autouse=True)
def reset_llm_logger():
    root = logging.getLogger("llm")
    original_handlers = list(root.handlers)
    original_level = root.level
    root.handlers.clear()
    yield
    root.handlers.clear()
    root.handlers.extend(original_handlers)
    root.setLevel(original_level)


def test_configure_logging_adds_stream_handler():
    configure_logging()

    handlers = logging.getLogger("llm").handlers
    assert any(isinstance(h, logging.StreamHandler) for h in handlers)


def test_configure_logging_handler_writes_to_stdout():
    configure_logging()

    stream_handlers = [
        h for h in logging.getLogger("llm").handlers if isinstance(h, logging.StreamHandler)
    ]
    assert stream_handlers[0].stream is sys.stdout


def test_configure_logging_sets_default_info_level():
    configure_logging()

    assert logging.getLogger("llm").level == logging.INFO


def test_configure_logging_sets_custom_debug_level():
    configure_logging(level="DEBUG")

    assert logging.getLogger("llm").level == logging.DEBUG


def test_configure_logging_sets_custom_warning_level():
    configure_logging(level="WARNING")

    assert logging.getLogger("llm").level == logging.WARNING


def test_configure_logging_does_not_add_duplicate_handlers():
    configure_logging()
    configure_logging()
    configure_logging()

    stream_handlers = [
        h for h in logging.getLogger("llm").handlers if isinstance(h, logging.StreamHandler)
    ]
    assert len(stream_handlers) == 1


def test_configure_logging_level_updated_on_every_call():
    configure_logging(level="DEBUG")
    configure_logging(level="WARNING")  # level always updated; only handler add is guarded

    assert logging.getLogger("llm").level == logging.WARNING


def test_audit_logger_name_is_llm_audit():
    assert audit_logger.name == "llm.audit"


def test_audit_logger_propagates_to_llm_parent():
    assert audit_logger.parent.name == "llm"
    assert audit_logger.propagate is True


def test_audit_logger_emits_at_info_when_configured(caplog):
    configure_logging()

    with caplog.at_level(logging.INFO, logger="llm.audit"):
        audit_logger.info("test message")

    assert any("test message" in r.getMessage() for r in caplog.records)


def test_llm_logger_effective_level_is_info_after_configure():
    configure_logging(level="INFO")

    # effective level on child logger must resolve to INFO via parent
    assert audit_logger.getEffectiveLevel() == logging.INFO
