"""Tests for core/logging.py.

This pins down a real regression: StructuredLogger's methods used to have their
print() call commented out, so every logger.info/warning/error/exception call in
the entire codebase was a silent no-op. These tests fail loudly if that happens again.
"""

from core.logging import get_structured_logger, StructuredLogger


class TestGetStructuredLogger:

    def test_returns_a_structured_logger(self):
        assert isinstance(get_structured_logger("test"), StructuredLogger)

    def test_carries_the_given_name(self):
        assert get_structured_logger("my.module").name == "my.module"


class TestLoggingActuallyLogs:
    """Each level method must produce visible output - that's the whole point of a logger."""

    def test_info_writes_to_stdout(self, capsys):
        get_structured_logger("test").info("hello info")
        out = capsys.readouterr().out
        assert "hello info" in out
        assert "INFO" in out

    def test_warning_writes_to_stdout(self, capsys):
        get_structured_logger("test").warning("hello warning")
        out = capsys.readouterr().out
        assert "hello warning" in out
        assert "WARNING" in out

    def test_error_writes_to_stdout(self, capsys):
        get_structured_logger("test").error("hello error")
        out = capsys.readouterr().out
        assert "hello error" in out
        assert "ERROR" in out

    def test_debug_writes_to_stdout(self, capsys):
        get_structured_logger("test").debug("hello debug")
        out = capsys.readouterr().out
        assert "hello debug" in out
        assert "DEBUG" in out

    def test_critical_writes_to_stdout(self, capsys):
        get_structured_logger("test").critical("hello critical")
        out = capsys.readouterr().out
        assert "hello critical" in out
        assert "CRITICAL" in out

    def test_message_includes_logger_name(self, capsys):
        get_structured_logger("my.module.path").info("a message")
        out = capsys.readouterr().out
        assert "my.module.path" in out

    def test_percent_style_args_are_interpolated(self, capsys):
        get_structured_logger("test").info("count is %s", 42)
        out = capsys.readouterr().out
        assert "count is 42" in out

    def test_message_without_args_is_not_percent_formatted(self):
        """A bare message containing a literal '%' must not raise even with no args."""
        get_structured_logger("test").info("100% done")

    def test_exception_logs_message_and_traceback(self, capsys):
        """The message goes through the normal stdout logger; the traceback itself
        goes via traceback.print_exc(), which writes to stderr - check both streams."""
        logger = get_structured_logger("test")
        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("something failed")
        captured = capsys.readouterr()
        assert "something failed" in captured.out
        assert "ValueError" in captured.err
        assert "boom" in captured.err


class TestCompatShims:
    """Legacy call sites use these extended methods - they must not raise."""

    def test_log_request_does_not_raise(self, capsys):
        get_structured_logger("test").log_request("GET", "/health")
        assert "request" in capsys.readouterr().out

    def test_log_database_operation_does_not_raise(self, capsys):
        get_structured_logger("test").log_database_operation("SELECT", table="users")
        assert "db" in capsys.readouterr().out

    def test_log_business_event_does_not_raise(self, capsys):
        get_structured_logger("test").log_business_event("order_placed")
        assert "event" in capsys.readouterr().out
