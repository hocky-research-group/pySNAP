import logging
import os
import pytest
from snap_workflow.utils.logging import setup_logging, logger, MinimalistFormatter


def test_setup_logging_default(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    setup_logging()
    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1


def test_setup_logging_env_debug(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    setup_logging()
    assert logger.level == logging.DEBUG


def test_setup_logging_env_warning(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    setup_logging()
    assert logger.level == logging.WARNING


def test_setup_logging_with_file_handler(tmp_path):
    log_file = str(tmp_path / "test.log")
    setup_logging(level=logging.INFO, log_file=log_file)
    assert len(logger.handlers) == 2
    logger.info("Test log entry")
    assert os.path.isfile(log_file)


def test_minimalist_formatter_levels():
    fmt_color = MinimalistFormatter(use_color=True, is_debug=True)
    fmt_plain = MinimalistFormatter(use_color=False, is_debug=False)

    rec_info = logging.LogRecord("test", logging.INFO, "path.py", 10, "info msg", (), None)
    rec_debug = logging.LogRecord("test", logging.DEBUG, "path.py", 15, "debug msg", (), None)
    rec_warn = logging.LogRecord("test", logging.WARNING, "path.py", 20, "warn msg", (), None)
    rec_err = logging.LogRecord("test", logging.ERROR, "path.py", 25, "error msg", (), None)

    assert "info msg" in fmt_plain.format(rec_info)
    assert "DEBUG" in fmt_color.format(rec_debug)
    assert "WARN" in fmt_color.format(rec_warn)
    assert "ERROR" in fmt_color.format(rec_err)
