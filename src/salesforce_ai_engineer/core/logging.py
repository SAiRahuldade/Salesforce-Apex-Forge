"""Rich-powered logging configuration."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

from salesforce_ai_engineer.config.settings import LoggingConfig


LOG_FORMAT = "%(message)s"
FILE_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(config: LoggingConfig, app_name: str) -> logging.Logger:
    """Configure console and file logging for the whole process."""

    config.directory.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, config.level.upper(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    rich_handler = RichHandler(
        rich_tracebacks=config.rich_tracebacks,
        show_path=False,
        markup=True,
    )
    rich_handler.setLevel(level)
    rich_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    file_handler = RotatingFileHandler(
        Path(config.directory) / f"{app_name}.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(FILE_LOG_FORMAT))

    root.addHandler(rich_handler)
    root.addHandler(file_handler)
    return logging.getLogger(app_name)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

