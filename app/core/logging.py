"""Yapılandırılmış log kurulumu.

`get_logger(__name__)` ile her modül logger alır. `setup_logging()` idempotenttir;
ilk çağrıda kök logger'ı yapılandırır, sonrakiler yok sayılır.

`LOG_FORMAT=json` ise stdout JSON satırları üretir (parsing-friendly,
production'da log aggregator için tercih edilir). Default `text` — geliştirme
için okunabilir.
"""

from __future__ import annotations

import json
import logging
import sys

from app.core.config import LogLevel, get_settings

_configured = False


class JsonFormatter(logging.Formatter):
    """Her log satırını tek satırlık JSON olarak üretir."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: LogLevel | None = None) -> None:
    global _configured
    if _configured:
        return

    s = get_settings()
    log_level = level or s.log_level

    root = logging.getLogger()
    root.setLevel(log_level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    if s.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
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
