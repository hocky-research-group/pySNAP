import os
import logging

logger = logging.getLogger("snap_workflow")


def setup_logging(level=None, log_file=None):
    """
    Configure the central logger with stream and optional file handlers.
    Supports LOG_LEVEL environment variable (e.g. DEBUG, INFO, WARNING, ERROR).
    Formats standard logs cleanly without internal line numbers unless level is DEBUG.
    """
    if level is None:
        env_level = os.getenv("LOG_LEVEL", "INFO").upper()
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "WARN": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        level = level_map.get(env_level, logging.INFO)

    logger.setLevel(level)
    logger.handlers.clear()

    if level <= logging.DEBUG:
        fmt_str = "[%(asctime)s] %(levelname)s [%(name)s:%(filename)s:%(lineno)d] %(message)s"
    else:
        fmt_str = "[%(asctime)s] %(levelname)s: %(message)s"

    formatter = logging.Formatter(fmt_str, datefmt="%Y-%m-%d %H:%M:%S")

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
