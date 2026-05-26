"""Commentator arayüzü — [BOŞ İSKELET, Faz 3'te doldurulacak].

Engine'in ürettiği sayısal sonuçları insan diliyle açıklayan katmanın sözleşmesi.
Şimdilik sadece imza; mantık yok.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Commentator(ABC):
    @abstractmethod
    def explain(self, engine_output: Any) -> str:
        """Motor çıktısını insan diline çevirir."""
