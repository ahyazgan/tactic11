"""API çağrısı / token kullanım takipçisi + eşik koruması.

`record_call()` her dış istek için bir satır yazar. `guard_quota()` çağrı
ÖNCE yapılır; günlük/aylık eşiğe yaklaşıldığında uyarır, aşıldığında
`QuotaExceeded` fırlatır.

Sözleşme:
- `source="api_football"` → çağrı sayısı (günlük + aylık)
- `source="anthropic"` → token toplamı (günlük)
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db import models

log = get_logger(__name__)


class QuotaExceeded(RuntimeError):
    pass


def _warn_fraction() -> float:
    """Settings'ten çağrı anında okur — testlerin monkeypatch'i etkili olsun."""
    return get_settings().quota_warn_fraction


def record_call(
    session: Session, *, source: str, endpoint: str, tokens: int = 0
) -> None:
    session.add(
        models.UsageEvent(
            source=source,
            endpoint=endpoint,
            tokens=tokens,
            created_at=datetime.now(UTC),
        )
    )
    session.flush()


def _count(session: Session, source: str, since: datetime) -> int:
    return session.scalar(
        select(func.count())
        .select_from(models.UsageEvent)
        .where(
            models.UsageEvent.source == source,
            models.UsageEvent.created_at >= since,
        )
    ) or 0


def _token_sum(session: Session, source: str, since: datetime) -> int:
    return session.scalar(
        select(func.coalesce(func.sum(models.UsageEvent.tokens), 0))
        .select_from(models.UsageEvent)
        .where(
            models.UsageEvent.source == source,
            models.UsageEvent.created_at >= since,
        )
    ) or 0


def consume_quota(
    session: Session,
    *,
    source: str,
    endpoint: str,
    tokens: int = 0,
) -> None:
    """Atomik: guard_quota + record_call tek transaction'da.

    Akış: önce mevcut sayıma karşı `guard_quota` çağrılır (henüz bu kaydı
    saymadan), geçtiyse `record_call` ile satır eklenir. İkisi tek transaction
    içinde olduğu için "ayrı `with SessionLocal()` blokları arasında pencere"
    yarışı kapanır.

    Çoklu-süreç tam atomicity için Postgres SERIALIZABLE isolation önerilir
    (SQLite zaten tek-yazıcı). Cron tek-süreçli kullanım için yeterli.
    """
    guard_quota(session, source)
    record_call(session, source=source, endpoint=endpoint, tokens=tokens)


def guard_quota(session: Session, source: str) -> None:
    s = get_settings()
    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_month = start_of_day.replace(day=1)

    if source == "api_football":
        day = _count(session, source, start_of_day)
        if day >= s.api_football_daily_limit:
            raise QuotaExceeded(
                f"api_football günlük kota aşıldı: {day}/{s.api_football_daily_limit}"
            )
        if day >= s.api_football_daily_limit * _warn_fraction():
            log.warning(
                "api_football günlük kotaya yaklaşıldı: %d/%d",
                day,
                s.api_football_daily_limit,
            )

        month = _count(session, source, start_of_month)
        if month >= s.api_football_monthly_limit:
            raise QuotaExceeded(
                f"api_football aylık kota aşıldı: {month}/{s.api_football_monthly_limit}"
            )
        if month >= s.api_football_monthly_limit * _warn_fraction():
            log.warning(
                "api_football aylık kotaya yaklaşıldı: %d/%d",
                month,
                s.api_football_monthly_limit,
            )

    elif source == "anthropic":
        tokens = _token_sum(session, source, start_of_day)
        if tokens >= s.anthropic_daily_token_limit:
            raise QuotaExceeded(
                f"anthropic günlük token kotası aşıldı: {tokens}/{s.anthropic_daily_token_limit}"
            )
        if tokens >= s.anthropic_daily_token_limit * _warn_fraction():
            log.warning(
                "anthropic günlük token kotasına yaklaşıldı: %d/%d",
                tokens,
                s.anthropic_daily_token_limit,
            )

    else:
        log.debug("guard_quota: tanımsız source=%s, kontrol atlandı", source)
