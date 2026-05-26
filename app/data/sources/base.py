"""DataSource arayüzü.

Tüm veri kaynağı adapter'ları (api_football, tracking, vb.) bu sınıftan türer.
Bu arayüz spordan ve sağlayıcıdan bağımsız sözleşmedir; üst katmanlar adapter'a
değil arayüze konuşur. Faz 1'de api_football bunu doldurur; Faz 6'da tracking
adapter aynı arayüze uyar.

İçerik Faz 1'de yazılacak. Şimdilik sadece imzalar.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DataSource(ABC):
    """Bir dış veri kaynağını temsil eden adapter sözleşmesi."""

    name: str  # ör: "api_football", "tracking_xyz"

    @abstractmethod
    def get_leagues(self) -> list[Any]:
        """Kaynaktaki ligleri döndürür (domain.League listesi)."""

    @abstractmethod
    def get_teams(self, league_id: int, season: int) -> list[Any]:
        """Bir lig+sezondaki takımları döndürür (domain.Team listesi)."""

    @abstractmethod
    def get_team_matches(self, team_id: int, last_n: int) -> list[Any]:
        """Bir takımın son N maçını döndürür (domain.Match listesi)."""
