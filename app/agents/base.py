"""Agent arayüzü — [BOŞ İSKELET, Ufuk 3'te doldurulacak].

Otomasyon/ajan katmanının sözleşmesi. Tetiklenebilir bir görev birimi.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Agent(ABC):
    name: str

    @abstractmethod
    def run(self, context: Any) -> Any:
        """Ajanı bir bağlam ile çalıştır, sonucu döndür."""
