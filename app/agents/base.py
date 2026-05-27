"""Agent arayüzü — proaktif otomasyon birimi.

Bir Agent: scheduler'dan tetiklenebilir, engine'leri + AI'yi kullanarak
bir konu hakkında yapılandırılmış çıktı üreten birim. Klasik engine
"saf hesap"tan farklı olarak agent'lar AI commentator'a hit edebilir
ve yan etki (cache/quota) tetikleyebilir.

Pattern:
1. Scheduler `agent.run(session, context)` çağırır
2. Agent engine'leri kullanır, opsiyonel AI commentator
3. AgentResult döner — orchestrator (caller) `save_agent_output` ile DB'ye
   yazar
4. Idempotency: aynı (agent, version, subject) yeniden → mevcut satır update

Yan etkiler engine kuralı'nı bozmaz — agent kendisi DB'ye yazmaz, sadece
result döner; persistence ayrı bir katman.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class AgentResult:
    """Bir agent çalıştırmasının yapılandırılmış çıktısı.

    `output_json` ana payload (dashboard/UI okur); `summary` kısa metin
    (e-posta/Slack notify için). `subject_type` + `subject_id` hangi konu
    için üretildiği (match, team, player).
    """
    output_json: dict[str, Any]
    summary: str
    subject_type: str  # "match" | "team" | "player"
    subject_id: int


class Agent(ABC):
    """Bir agent'ın sözleşmesi.

    Concrete agent class'ları `name` + `version` set'ler ve `run()` implement
    eder. Subclass'lar genelde engine'leri tüketir; AI commentator opsiyonel.
    """

    name: str  # ör: "pre_match_report"
    version: str  # ör: "1"

    @abstractmethod
    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        """Bağlamla çalıştır; AgentResult döner.

        `context` agent-spesifik (ör: PreMatchReportAgent için
        `{"match_external_id": 99}`). Eksik anahtar → KeyError veya custom
        ValueError; orchestrator hata kaydeder.
        """
