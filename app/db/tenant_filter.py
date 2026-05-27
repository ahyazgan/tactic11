"""SQLAlchemy tenant filtering — global `with_loader_criteria` event listener.

Bir request başında `set_current_tenant_id(uuid)` çağrılır; bu listener
her ORM query'sine `WHERE table.tenant_id = current_tenant_id()` ekler.

Bypass: `with tenant_bypass(): ...` — super-admin cross-tenant query'lerinde
explicit kullanılır. Bu durumda listener kayıt yine çalışır ama filtre
eklemez.

`tenants`/`users`/`refresh_tokens` tabloları DİREKT filtre edilmez —
auth katmanı tenant ayrımını kendi yapar.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from app.db import models
from app.db.tenant_context import current_tenant_id, is_bypassed

# tenant_id taşıyan domain modeller — listener bu modellere filtre ekler.
_TENANT_MODELS = (
    models.League, models.Team, models.Player, models.Match,
    models.Snapshot, models.UsageEvent, models.CacheEntry, models.JobRun,
    models.PlayerAppearance, models.AgentOutput, models.Prediction,
    models.TrackingFrameRow, models.AssistantMemory,
    models.ChatConversation, models.ChatMessage, models.ScoutWatchlist,
)


def install_tenant_filter() -> None:
    """Global event listener kur — Session.do_orm_execute her query'de tetiklenir.

    İdempotent: tekrar çağrılırsa zaten kayıtlı listener'a dokunmaz.
    Test'ler veya app boot bu fonksiyonu çağırır.
    """
    if getattr(install_tenant_filter, "_installed", False):
        return

    @event.listens_for(Session, "do_orm_execute")
    def _add_tenant_filter(execute_state):
        # Bypass açık → hiçbir filtre ekleme
        if is_bypassed():
            return
        tid = current_tenant_id()
        if tid is None:
            # ContextVar set'li değil → filtre uygulamadan geç (test/mevcut kod)
            return
        # SELECT/UPDATE/DELETE'lere uygula; INSERT'lere değil
        if not execute_state.is_select and not (
            execute_state.is_update or execute_state.is_delete
        ):
            return
        for model in _TENANT_MODELS:
            execute_state.statement = execute_state.statement.options(
                with_loader_criteria(
                    model, lambda cls: cls.tenant_id == tid,
                    include_aliases=True,
                ),
            )

    install_tenant_filter._installed = True  # type: ignore[attr-defined]


def uninstall_tenant_filter() -> None:
    """Test cleanup için — event listener'ı kaldırır.

    `event.remove` runtime'da çalışmıyorsa (Session sınıf-bazlı) yine de
    `_installed` flag'i sıfırlanır; testler izolasyonu ContextVar set'leme
    ile sağlamalı.
    """
    install_tenant_filter._installed = False  # type: ignore[attr-defined]
