"""GuetLinker logging module.

Configures application-wide logging with daily file rotation.
"""

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from src.core.config import LOG_DIR


def setup_logger(level: int = logging.INFO) -> logging.Logger:
    """Set up the application logger with console and file handlers.

    Args:
        level: Logging level (default INFO).

    Returns:
        Configured root logger.
    """
    root = logging.getLogger("guetlinker")
    root.setLevel(level)

    # Avoid duplicate handlers on repeated calls
    if root.handlers:
        return root

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] [PID:%(process)d] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # File handler with daily rotation
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        filename=LOG_DIR / "guetlinker.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d.log"
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    return root


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the guetlinker namespace."""
    return logging.getLogger(f"guetlinker.{name}")
