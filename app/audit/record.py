"""Motor sonucunun yanında taşıdığı izlenebilirlik kaydı.

Engine fonksiyonları DB'ye yazmaz; sonuç + gerekçeyi `EngineResult` ile döner.
Orkestrasyon (örn. analiz endpoint'i ya da scheduler) `audit/base.AuditRecorder`
arayüzüyle bunu kalıcı yazar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

T = TypeVar("T")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AuditRecord:
    """Bir motor çıktısının "neye dayandığı" izini taşır.

    `subject_type` + `subject_id` neyle ilgili olduğunu (`team:611`),
    `metric` ne hesaplandığını (`form_score`), `inputs` formüle giren ham
    sayıları, `formula` insan-okur kısa açıklamayı tutar.
    """

    engine: str
    engine_version: str
    subject_type: str
    subject_id: int
    metric: str
    value: Any
    inputs: dict[str, Any]
    formula: str
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class EngineResult(Generic[T]):
    value: T
    audit: AuditRecord
