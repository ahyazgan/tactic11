"""Audit kaydının iskelet sözleşmesi — [Faz 2'de doldurulacak].

Bir motor sonucunun "neye dayandığı" izini tutan veri yapısının taslağı.
Şimdi sadece şekil belli olsun diye bırakıldı; gerçek tablo/repository Faz 2'de
yazılacak.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AuditRecorder(ABC):
    @abstractmethod
    def record(
        self,
        *,
        subject_type: str,
        subject_id: int,
        metric: str,
        value: Any,
        inputs: dict,
        engine_version: str,
        explanation: str | None = None,
    ) -> None:
        """Bir motor/AI çıktısının kaynak metriklerle birlikte izini saklar."""
