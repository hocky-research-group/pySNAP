import logging
import os
import pytest
from snap_workflow.utils.logging import setup_logging, logger


def test_setup_logging_default(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    setup_logging()
    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1
    assert "%(filename)s" not in logger.handlers[0].formatter._fmt


def test_setup_logging_env_debug(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    setup_logging()
    assert logger.level == logging.DEBUG
    assert "%(filename)s" in logger.handlers[0].formatter._fmt


def test_setup_logging_env_warning(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    setup_logging()
    assert logger.level == logging.WARNING
