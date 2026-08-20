import os
import sys
import logging

logger = logging.getLogger("snap_workflow")


class MinimalistFormatter(logging.Formatter):
    """
    Clean, minimalist log formatter for CLI interaction.
    Omits 'INFO:' tags to remove visual clutter, formats time as HH:MM:SS,
    and applies ANSI color highlighting to warnings, errors, and debug logs.
    """

    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD_YELLOW = "\033[1;33m"
    BOLD_RED = "\033[1;31m"

    def __init__(self, use_color=True, is_debug=False):
        fmt = "[%(asctime)s] %(levelname)s [%(name)s:%(filename)s:%(lineno)d] %(message)s" if is_debug else "%(message)s"
        super().__init__(fmt=fmt, datefmt="%H:%M:%S")
        self.use_color = use_color and hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        self.is_debug = is_debug

    def format(self, record):
        time_str = self.formatTime(record, self.datefmt)
        msg = record.getMessage()

        if self.is_debug:
            msg = f"[{record.name}:{record.filename}:{record.lineno}] {msg}"

        if record.levelno >= logging.ERROR:
            level_tag = f"{self.BOLD_RED}ERROR{self.RESET} " if self.use_color else "ERROR "
        elif record.levelno >= logging.WARNING:
            level_tag = f"{self.BOLD_YELLOW}WARN{self.RESET}  " if self.use_color else "WARN  "
        elif record.levelno <= logging.DEBUG:
            level_tag = f"{self.DIM}DEBUG{self.RESET} " if self.use_color else "DEBUG "
        else:
            level_tag = ""

        time_prefix = f"{self.DIM}{time_str}{self.RESET}" if self.use_color else time_str
        return f"{time_prefix}  {level_tag}{msg}"


def setup_logging(level=None, log_file=None):
    """
    Configure the central logger with stream and optional file handlers.
    Supports LOG_LEVEL environment variable (e.g. DEBUG, INFO, WARNING, ERROR).
    Formats standard logs cleanly without internal line numbers or INFO prefixes unless level is DEBUG.
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

    is_debug = (level <= logging.DEBUG)
    console_formatter = MinimalistFormatter(use_color=True, is_debug=is_debug)

    ch = logging.StreamHandler()
    ch.setFormatter(console_formatter)
    logger.addHandler(ch)

    if log_file:
        file_formatter = MinimalistFormatter(use_color=False, is_debug=is_debug)
        fh = logging.FileHandler(log_file)
        fh.setFormatter(file_formatter)
        logger.addHandler(fh)
