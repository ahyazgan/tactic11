"""Request-scoped context (request_id, vs.).

ContextVar tabanlı — async/sync ikisinde de doğru context'i taşır.
Middleware her HTTP isteği başlangıcında `set_request_id` çağırır; logging
filter'ı her log satırına otomatik enjekte eder.

Bu modül kasıtlı olarak küçük + bağımsız: ne `app.api`'ye ne `app.db`'ye
bağlı. Hem `app.core.logging` (LogRecord enjeksiyonu) hem `app.api.main`
(middleware set/clear) buradan okur — döngü olmaz.
"""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return request_id_var.get()


def set_request_id(rid: str) -> None:
    request_id_var.set(rid)


def clear_request_id() -> None:
    request_id_var.set(None)
