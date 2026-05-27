"""Yapılandırılmış log kurulumu.

`get_logger(__name__)` ile her modül logger alır. `setup_logging()` idempotenttir;
ilk çağrıda kök logger'ı yapılandırır, sonrakiler yok sayılır.
"""

from __future__ import annotations

import logging
import sys

from app.core.config import LogLevel, get_settings

_configured = False


def setup_logging(level: LogLevel | None = None) -> None:
    global _configured
    if _configured:
        return

    log_level = level or get_settings().log_level

    root = logging.getLogger()
    root.setLevel(log_level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
