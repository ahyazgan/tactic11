"""Yapılandırılmış log kurulumu.

`get_logger(__name__)` ile her modül logger alır. `setup_logging()` idempotenttir;
ilk çağrıda kök logger'ı yapılandırır, sonrakiler yok sayılır.

`LOG_FORMAT=json` ise stdout JSON satırları üretir (parsing-friendly,
production'da log aggregator için tercih edilir). Default `text` — geliştirme
için okunabilir.

**Request ID propagation:** `RequestIdFilter` her LogRecord'a varsa contextvar'dan
`request_id`'yi ekler. JSON modunda payload alanı olarak, text modunda satırın
sonuna `[req=...]` ekiyle çıkar. Set'lemek middleware'in sorumluluğu
(`app.core.request_context.set_request_id`).
"""

from __future__ import annotations

import json
import logging
import sys

from app.core.config import LogLevel, get_settings
from app.core.request_context import get_request_id

_configured = False


class RequestIdFilter(logging.Filter):
    """Her LogRecord'a varsa request_id'yi ekler.

    Filter zincirinin başında çalışır → tüm handler'lar etiketlenmiş kaydı görür.
    Set'li değilse alan eklenmez (text formatında parazit yok).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        rid = get_request_id()
        if rid is not None:
            record.request_id = rid
        return True


class JsonFormatter(logging.Formatter):
    """Her log satırını tek satırlık JSON olarak üretir."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = getattr(record, "request_id", None)
        if rid:
            payload["request_id"] = rid
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatterWithRequestId(logging.Formatter):
    """Default text format + (varsa) sonda [req=...] eki."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        rid = getattr(record, "request_id", None)
        if rid:
            return f"{base} [req={rid}]"
        return base


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
    handler.addFilter(RequestIdFilter())
    if s.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            TextFormatterWithRequestId(
                fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
