"""SQLAlchemy ORM modelleri.

Tablolar domain modelleriyle bire bir eşleşir; çevirme `data/ingest/` katmanında
yapılır. `tenant_id` bugün yok ama indeks tasarımı sonradan eklemeyi kolaylaştıracak
şekilde basit.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class League(Base):
    __tablename__ = "leagues"
    __table_args__ = (
        UniqueConstraint(
            "sport", "external_id", "season", "tenant_id",
            name="uq_leagues_sport_extid_season",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    season: Mapped[int] = mapped_column(Integer, index=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("sport", "external_id", "tenant_id", name="uq_teams_sport_extid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    founded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("sport", "external_id", "tenant_id", name="uq_players_sport_extid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(8), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint(
            "sport", "external_id", "tenant_id", name="uq_matches_sport_extid",
        ),
        Index("ix_matches_league_season", "league_external_id", "season"),
        Index("ix_matches_kickoff", "kickoff"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[int] = mapped_column(Integer, index=True)
    league_external_id: Mapped[int] = mapped_column(Integer)
    season: Mapped[int] = mapped_column(Integer)
    kickoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(8))
    home_team_external_id: Mapped[int] = mapped_column(Integer)
    away_team_external_id: Mapped[int] = mapped_column(Integer)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class Snapshot(Base):
    """Bir sync sonunda durumun fotoğrafı.

    Üzerine yazılmaz; her sync yeni satır ekler. `scope` örn:
    `"league:203:season:2024"`.
    """

    __tablename__ = "snapshots"
    __table_args__ = (
        Index("ix_snapshots_sport_scope_created", "sport", "scope", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    leagues_count: Mapped[int] = mapped_column(Integer)
    teams_count: Mapped[int] = mapped_column(Integer)
    matches_count: Mapped[int] = mapped_column(Integer)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class UsageEvent(Base):
    """Her dış servis çağrısı için bir kayıt (kota koruması ve maliyet izleme)."""

    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_source_created", "source", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    endpoint: Mapped[str] = mapped_column(String(255))
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class CacheEntry(Base):
    """Adapter yanıtları için TTL'li cache satırı."""

    __tablename__ = "cache_entries"
    __table_args__ = (
        PrimaryKeyConstraint("source", "key", name="pk_cache_entries"),
        Index("ix_cache_entries_expires", "expires_at"),
    )

    source: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(512))
    value: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class JobRun(Base):
    """Scheduler bir job'u çalıştırdığında kayıt; bir job çağrısı = bir satır.

    `status`: running | success | failed. `attempts` deneme sayısı (retry
    sonrası nihai). Başarısız son denemeden gelen hata `error`'a yazılır.
    """

    __tablename__ = "job_runs"
    __table_args__ = (
        Index("ix_job_runs_name_started", "job_name", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64))
    args: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class PlayerAppearance(Base):
    """Bir oyuncunun bir maçtaki dakika kaydı.

    Lineup adapter (Faz 6) bu tabloyu dolduracak; şu an boş kalır. Engine
    (`engine.load`) bu satırları okuyup oyuncu yük raporu üretir.
    """

    __tablename__ = "player_appearances"
    __table_args__ = (
        UniqueConstraint(
            "sport", "player_external_id", "match_external_id", "tenant_id",
            name="uq_player_appearances_player_match",
        ),
        Index(
            "ix_player_appearances_player_kickoff",
            "player_external_id", "kickoff",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(32))
    player_external_id: Mapped[int] = mapped_column(Integer)
    match_external_id: Mapped[int] = mapped_column(Integer)
    minutes: Mapped[int] = mapped_column(Integer)
    kickoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )
    # Prompt 4 — API-Football fixture/players ingest
    team_external_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating_apifootball: Mapped[float | None] = mapped_column(Float, nullable=True)
    passes_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passes_accuracy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_on: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dribbles_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dribbles_success: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fouls_committed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fouls_drawn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    red_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    second_yellow: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    substituted_in_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    substituted_out_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position_played: Mapped[str | None] = mapped_column(String(5), nullable=True)
    formation_played: Mapped[str | None] = mapped_column(String(10), nullable=True)
    captain: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class AgentOutput(Base):
    """Bir agent çalıştırmasının kalıcı sonucu.

    Idempotency: aynı (agent_name, agent_version, subject_type, subject_id)
    yeniden çalıştırılırsa yeni satır oluşmaz; output_json + summary +
    updated_at refresh edilir.

    Engine'lerin AuditRecord-bazlı sonuçlarından farklı: agent'lar AI'yi de
    kullanır ve "human-readable summary" üretir; dashboard direkt buradan
    okuyabilir.
    """

    __tablename__ = "agent_outputs"
    __table_args__ = (
        UniqueConstraint(
            "agent_name", "agent_version", "subject_type", "subject_id", "tenant_id",
            name="uq_agent_outputs_request",
        ),
        Index(
            "ix_agent_outputs_agent_subject",
            "agent_name", "subject_type", "subject_id",
        ),
        Index("ix_agent_outputs_updated", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(64))
    agent_version: Mapped[str] = mapped_column(String(16))
    subject_type: Mapped[str] = mapped_column(String(16))  # "match"|"team"|"player"
    subject_id: Mapped[int] = mapped_column(Integer)
    output_json: Mapped[str] = mapped_column(Text)  # serialized AgentResult.output_json
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class Prediction(Base):
    """Bir engine'in bir maç için yaptığı tahmin (kalibrasyon için kalıcı).

    Idempotency: aynı (match, engine, engine_version, params_hash) yeniden
    çağrılırsa yeni satır oluşmaz; mevcut satır predicted_value_json + updated_at
    ile yenilenir.

    Actual sütunları: maç bittiğinde reconcile job dolduracak (PR B2).
    """

    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint(
            "sport", "match_external_id", "engine", "engine_version", "params_hash", "tenant_id",
            name="uq_predictions_unique_request",
        ),
        Index("ix_predictions_match", "sport", "match_external_id"),
        Index("ix_predictions_engine_version", "engine", "engine_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(32))
    match_external_id: Mapped[int] = mapped_column(Integer)
    engine: Mapped[str] = mapped_column(String(64))  # ör: "engine.predict"
    engine_version: Mapped[str] = mapped_column(String(16))
    params_hash: Mapped[str] = mapped_column(String(64))  # input params'in sha256[:32]
    params_json: Mapped[str] = mapped_column(Text)  # hangi rho/last_n vb. kullanıldı
    predicted_value_json: Mapped[str] = mapped_column(Text)  # tahmin payload
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Reconciliation (PR B2 dolduracak)
    actual_home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_outcome: Mapped[str | None] = mapped_column(
        String(4), nullable=True
    )  # "home" | "draw" | "away" | None
    reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class TrackingFrameRow(Base):
    """Bir maçın bir anının tüm oyuncu pozisyonları (tracking ingest).

    Yüksek hacimli: tipik maç 25 Hz × 90 dk ≈ 135k frame; bizim test
    fixture 30 frame. Per-player satıra split etmek yerine players_json
    içinde toplu sakla — ingest hızı + okuma da batch'le yapılıyor.

    Idempotency: aynı (match_external_id, timestamp) yeniden ingest
    edilirse mevcut satır güncellenir. Bir maçı tamamen yeniden çekmek
    için önce silip sonra ingest etmek caller'ın sorumluluğu (`ingest_tracking_match`).
    """

    __tablename__ = "tracking_frames"
    __table_args__ = (
        UniqueConstraint(
            "sport", "match_external_id", "timestamp", "tenant_id",
            name="uq_tracking_frame_unique",
        ),
        Index("ix_tracking_match_time", "sport", "match_external_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(String(32))
    match_external_id: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period: Mapped[int] = mapped_column(Integer)
    minute: Mapped[float] = mapped_column(Float)
    ball_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    ball_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    players_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class AssistantMemory(Base):
    """Manager asistanın takım/sezon-bazlı kalıcı hafızası.

    Key-value: (subject_type, subject_id) altında namespaced key'ler.
    Örnek subject_type: "team", "league"; key: "preferred_formation",
    "playing_style", "last_decision_context", "user_notes".

    Idempotent: aynı (subject_type, subject_id, key) → update.
    """

    __tablename__ = "assistant_memory"
    __table_args__ = (
        UniqueConstraint(
            "subject_type", "subject_id", "key", "tenant_id",
            name="uq_assistant_memory_request",
        ),
        Index("ix_assistant_memory_subject", "subject_type", "subject_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(16))  # "team" | "league"
    subject_id: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(64))
    value_json: Mapped[str] = mapped_column(Text)  # serialize edilmiş any-type
    created_at_: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=True),
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class ChatConversation(Base):
    """Asistan chat geçmişi için konuşma kaydı.

    Bir konuşma birden çok mesajdan oluşur (ChatMessage). Opsiyonel
    team_external_id ile hangi takımın bağlamında konuşulduğu işaretlenir.
    """

    __tablename__ = "chat_conversations"
    __table_args__ = (
        Index("ix_chat_conversations_team", "team_external_id"),
        Index("ix_chat_conversations_updated", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_external_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class ScoutWatchlist(Base):
    """Scout şefi izleme listesi.

    Bir kullanıcı (user_id şu an "default" — multi-tenant geldikten sonra
    gerçekleşecek) bir oyuncuyu işaretler; notes opsiyonel. Scheduler haftalık
    bu watchlist'i tarayıp performans alert'leri üretir.
    """

    __tablename__ = "scout_watchlist"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "player_external_id", "tenant_id",
            name="uq_scout_watchlist_user_player",
        ),
        Index("ix_scout_watchlist_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), default="default")
    player_external_id: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


class ChatMessage(Base):
    """Konuşma içindeki bir mesaj (user veya assistant).

    `content_json` Anthropic format'ında content list (user için string ya da
    tool_result; assistant için text + tool_use). Tool izlerini de tutar
    (tool_traces_json) — UI/audit için.
    """

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_conv_seq", "conversation_id", "seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)  # konuşmadaki sıra
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content_json: Mapped[str] = mapped_column(Text)
    tool_traces_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )


# --------------------------------------------------------------------------- #
# Multi-tenant (Ufuk 1): tenants + users + refresh_tokens
# --------------------------------------------------------------------------- #


class Tenant(Base):
    """Tenant = bir kulüp / bir müşteri. Tüm domain verisi tenant_id ile izole.

    `id` UUID string (36 karakter) — SQLite + Postgres uyumlu, ORM string olarak
    tutar (FK string). `slug` URL-safe kısa kimlik; unique. `settings` JSON
    (Text) — webhook, brand config, scheduler cron override vs.
    """

    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenants_slug"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class User(Base):
    """Kullanıcı — bir tenant'a bağlı. Email unique per tenant (cross-tenant
    aynı email olabilir).

    `role`: admin | analyst | coach | viewer.
    `password_hash`: bcrypt çıktısı (60 karakter). Asla loglanmaz.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        Index("ix_users_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"),
    )
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(16))  # admin|analyst|coach|viewer
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


class RefreshToken(Base):
    """JWT refresh token — server-side revocable. token_hash bcrypt değil,
    SHA-256 — refresh token'i tek tek doğrularken bcrypt yavaş olur ve secret
    olarak yeterli (refresh token uzun random string zaten).
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_hash"),
        Index("ix_refresh_tokens_user", "user_id"),
        Index("ix_refresh_tokens_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
    )
    token_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

