"""Canlı maçta kadro ve değişiklik girişi — video hattı ile karar hattını bağlar.

## Neden bu modül var

Hat şudur: video → takip → olaylar → karar paneli. İlk üç halka çalışıyor, ama
karar katmanının iki tablosu videodan ÇIKMAYAN bilgiye muhtaç:

- **Ne zaman değiştir?** (`sub_timing`) → o ana kadar kaç değişiklik yapıldı
- **Kimi çıkar?** (`live_sub_recommendation`) → sahada kim var, kim ilk 11'di

Takip sistemi sahada 22 anonim iz görür; kimin kim olduğunu ve kimin sonradan
girdiğini bilmez (`TrackingIdentity` eşlemesi de elle girilir). Kadro
girilmezse `player_appearances` boş kalır, `subs_used` ve `off_prior` None
gider ve iki tablo da SESSİZCE devre dışı kalır — panel boş öneri döner.

Bu modül o eksik halkayı kapatır: maç başında ilk 11, maç içinde her değişiklik
tek çağrıyla girilir. Bilgi zaten koçun yanındadır; videodan çıkarmaya
çalışmak (forma numarası okumak) ayrı ve çok daha zor bir iştir.

## `applied` neden otomatik işaretlenmiyor

Değişiklik girildiğinde sistem, o oyuncunun son önerilerin aday listesinde olup
olmadığını görebilir ve görür de (`uyusma` alanı). Ama bunu `applied=true`
yapmaz.

`applied` "koç bu öneri YÜZÜNDEN yaptı" demektir ve karşı-olgu ölçümünün tek
dayanağıdır (`decision_uplift`, karnenin Karşı-olgu boyutu). Koçun zaten
yapacağı bir değişikliği bizim listemizde göründü diye "uygulandı" saymak,
ölçülmek istenen nedenselliği uydurmaktır — ve tam olarak eksikliğinden
şikâyet ettiğimiz veriyi sahte üretir. Uyuşma GÖZLEMdir, işaret KOÇUN
beyanıdır; ikisi ayrı alanlarda durur.

Uyuşma bilgisi panele tek dokunuşluk işaretlemeyi kolaylaştırmak için döner:
`POST /admin/decisions/{id}/applied`.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.db.match_load import MatchLoadSample
from app.db.session import get_session
from app.sports import football

router = APIRouter(prefix="/admin", tags=["admin"])

# Canlı maçta "oynadığı dakika" o ANA kadarkidir; maç bitince son değer kalır.
# Yükleyici (`load_match_appearances`) ilk 11 için minutes > 0 ister, bu yüzden
# maçın ilk dakikasında bile en az 1 yazılır.
MIN_PLAYED_MINUTES = 1
# Öneri uyuşması bu kadar dakika GERİYE bakar (karnedeki öncü süre penceresi).
AGREEMENT_LOOKBACK_MIN = 15.0


def _whole_minute(minute: float) -> int:
    """`player_appearances` giriş/çıkış dakikalarını TAM SAYI tutar.

    Sağlayıcı verisi de öyledir (StatsBomb `minute` alanı tam dakikadır) ve
    zamanlama önseli 5 dakikalık bantlarla çalışır; yuvarlama ölçümü etkilemez.
    """
    return int(round(minute))


class LineupPlayer(BaseModel):
    player_external_id: int
    position: str | None = Field(default=None, max_length=8,
                                 description="GK/DC/MC/FC gibi mevki kodu")


class LineupIn(BaseModel):
    team_external_id: int
    starters: list[LineupPlayer] = Field(..., min_length=1, max_length=11)
    minute: float = Field(default=0.0, ge=0, le=130,
                          description="girişin yapıldığı maç dakikası")
    replace: bool = Field(default=False,
                          description="True → bu takımın önceki kayıtları silinir")


class SubstitutionIn(BaseModel):
    team_external_id: int
    minute: float = Field(..., ge=0, le=130)
    player_off: int
    player_on: int
    position: str | None = Field(default=None, max_length=8,
                                 description="girenin mevkisi; boşsa çıkanınki devralınır")


def _match_or_404(session: Session, match_id: int) -> models.Match:
    row = session.execute(select(models.Match).where(
        models.Match.sport == football.SPORT_NAME,
        models.Match.external_id == match_id,
    )).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"maç {match_id} yok")
    return row


def _rows_for(session: Session, match_id: int, team_id: int) -> list[models.PlayerAppearance]:
    return list(session.execute(select(models.PlayerAppearance).where(
        models.PlayerAppearance.sport == football.SPORT_NAME,
        models.PlayerAppearance.match_external_id == match_id,
        models.PlayerAppearance.team_external_id == team_id,
    )).scalars())


def _on_pitch(rows: list[models.PlayerAppearance], minute: float) -> list[models.PlayerAppearance]:
    """O an sahada olanlar. O DAKİKA GİREN sahadadır; o dakika çıkan da hâlâ sayılır
    (çıkış anının kendisi henüz geçmemiştir)."""
    return [r for r in rows
            if float(r.substituted_in_minute or 0) <= minute
            and (r.substituted_out_minute is None
                 or float(r.substituted_out_minute) >= minute)]


def _touch_minutes(rows: list[models.PlayerAppearance], minute: float) -> None:
    """Sahadakilerin 'oynadığı dakika'sını o ana taşı — canlı maçta bu sayı akar."""
    for r in rows:
        if r.substituted_out_minute is not None:
            continue
        played = max(MIN_PLAYED_MINUTES, int(minute - float(r.substituted_in_minute or 0)))
        r.minutes = played


def _subs_used(rows: list[models.PlayerAppearance], minute: float) -> int:
    """Kullanılmış hak = o ana kadar sahaya GİREN oyuncu sayısı (aynı dakikada
    iki oyuncu iki hak kullanır; tekilleştirilmez)."""
    return sum(1 for r in rows
               if r.substituted_in_minute is not None
               and float(r.substituted_in_minute) <= minute)


def _agreement(
    session: Session, match_id: int, team_id: int, minute: float, player_off: int,
) -> dict[str, Any]:
    """Çıkarılan oyuncu, son önerilerin aday listesinde miydi? GÖZLEMdir.

    `applied` işareti buradan TÜRETİLMEZ (modül doküstringi). Dönen kayıt panelin
    koça "bu öneriyi uyguladın mı?" diye tek dokunuşla sorabilmesi içindir.
    """
    import json

    rows = session.execute(select(models.Decision).where(
        models.Decision.sport == football.SPORT_NAME,
        models.Decision.match_external_id == match_id,
        models.Decision.team_external_id == team_id,
        models.Decision.minute >= minute - AGREEMENT_LOOKBACK_MIN,
        models.Decision.minute <= minute,
    )).scalars().all()
    matched: list[dict[str, Any]] = []
    for d in rows:
        try:
            ctx = json.loads(d.context_json or "{}")
        except (ValueError, TypeError):
            continue
        cands = ctx.get("sub_candidates") if isinstance(ctx, dict) else None
        if not isinstance(cands, list) or player_off not in [int(c) for c in cands]:
            continue
        matched.append({"decision_id": d.id, "minute": d.minute,
                        "sira": [int(c) for c in cands].index(player_off) + 1,
                        "applied": d.applied})
    return {
        "pencere_dk": AGREEMENT_LOOKBACK_MIN,
        "aday_listesinde_gecen_oneri": matched,
        "not": ("gözlem: çıkan oyuncu bu önerilerin listesindeydi. 'applied' "
                "işareti KOÇUN beyanıdır ve buradan türetilmez — "
                "POST /admin/decisions/{id}/applied"),
    }


class LoadSampleIn(BaseModel):
    player_external_id: int
    minute: float = Field(..., ge=0, le=130)
    total_distance_m: float | None = Field(default=None, ge=0)
    high_speed_m: float | None = Field(default=None, ge=0)
    sprint_m: float | None = Field(default=None, ge=0)
    accelerations: int | None = Field(default=None, ge=0)
    decelerations: int | None = Field(default=None, ge=0)
    device_load_au: float | None = Field(default=None, ge=0)
    max_speed_ms: float | None = Field(default=None, ge=0, le=15)


class LoadBatchIn(BaseModel):
    team_external_id: int
    source: str = Field(..., pattern="^(gps|tracking)$")
    speed_thresholds: str | None = Field(default=None, max_length=64,
                                         description="ör. 'hsr>5.5,sprint>7.0 m/s'")
    samples: list[LoadSampleIn] = Field(..., min_length=1, max_length=5000)


@router.post("/matches/{match_id}/load-samples", summary="Maç içi oyuncu yükü yaz (GPS/takip)")
def post_load_samples(
    match_id: int,
    payload: LoadBatchIn,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Maç İÇİNDE, dakika çözünürlüklü yük örneklerini yazar (upsert).

    Değerler **kümülatiftir**: maç başından o dakikaya kadarki toplam. Anlık
    değil kümülatif tutulur çünkü kümülatiften herhangi iki dakika arasındaki
    fark çıkarılabilir, tersi çıkarılamaz.

    `source="gps"` cihazdan gelen ölçümdür; `source="tracking"` video takibinden
    türetilmiştir ve oyuncu kimliği elle eşlendiği için aynı güvende sayılmaz —
    ölçüm raporunda ayrı ayrı değerlendirilir.

    Bu uç nokta veri TAŞIR. Yük sinyalinin öneriye bağlanması ayrı bir karardır
    ve ancak ön-kayıtlı sınav geçilirse yapılır (docs/MAC-ICI-YUK-PLANI.md).
    """
    _match_or_404(session, match_id)
    existing = {
        (r.player_external_id, r.minute): r
        for r in session.execute(select(MatchLoadSample).where(
            MatchLoadSample.match_external_id == match_id,
        )).scalars()
    }
    now = datetime.now(UTC)
    written = 0
    for smp in payload.samples:
        row = existing.get((smp.player_external_id, smp.minute))
        if row is None:
            row = MatchLoadSample(
                match_external_id=match_id, player_external_id=smp.player_external_id,
                minute=smp.minute, source=payload.source, created_at=now,
            )
            session.add(row)
        row.team_external_id = payload.team_external_id
        row.source = payload.source
        row.speed_thresholds = payload.speed_thresholds
        row.total_distance_m = smp.total_distance_m
        row.high_speed_m = smp.high_speed_m
        row.sprint_m = smp.sprint_m
        row.accelerations = smp.accelerations
        row.decelerations = smp.decelerations
        row.device_load_au = smp.device_load_au
        row.max_speed_ms = smp.max_speed_ms
        written += 1
    session.commit()
    total = session.execute(select(MatchLoadSample).where(
        MatchLoadSample.match_external_id == match_id,
    )).scalars().all()
    return {
        "match_external_id": match_id, "yazilan": written,
        "maçtaki_toplam_ornek": len(total),
        "oyuncu": len({r.player_external_id for r in total}),
        "kaynak": payload.source,
        "not": ("kümülatif değerler; yük sinyali ÖLÇÜLMEDEN öneriye bağlanmaz — "
                "docs/MAC-ICI-YUK-PLANI.md"),
    }


@router.get("/teams/{team_id}/squad", summary="Takımın oyuncu havuzu (kadro girişi için)")
def get_team_squad(
    team_id: int,
    limit: int = Query(default=40, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bu takım için geçmişte oynamış oyuncular — kadro giriş ekranının listesi.

    `players` tablosunda takım bağı YOKTUR; bağ yalnız maç kayıtlarında bulunur.
    Bu yüzden havuz `player_appearances`'tan türetilir ve en son oynayan başa
    gelir. Listede olmayan bir oyuncu (yeni transfer, altyapıdan çıkan) ekranda
    kimlikle elle girilebilir; uç nokta kapı değil kolaylıktır.
    """
    rows = session.execute(select(
        models.PlayerAppearance.player_external_id,
        models.PlayerAppearance.position_played,
        models.PlayerAppearance.kickoff,
    ).where(
        models.PlayerAppearance.sport == football.SPORT_NAME,
        models.PlayerAppearance.team_external_id == team_id,
    ).order_by(models.PlayerAppearance.kickoff.desc())).all()

    seen: dict[int, dict[str, Any]] = {}
    for pid, position, kickoff in rows:
        if pid in seen:
            continue
        seen[pid] = {"player_external_id": int(pid), "position": position,
                     "son_mac": kickoff.date().isoformat() if kickoff else None}
        if len(seen) >= limit:
            break
    if seen:
        names: dict[int, str] = {
            int(pid): str(name) for pid, name in session.execute(select(
                models.Player.external_id, models.Player.name,
            ).where(
                models.Player.sport == football.SPORT_NAME,
                models.Player.external_id.in_(list(seen)),
            ))
        }
        for pid, entry in seen.items():
            entry["name"] = names.get(pid)
    return {"team_external_id": team_id, "oyuncu": list(seen.values()),
            "not": ("havuz maç kayıtlarından türetildi; listede olmayan oyuncu "
                    "kimliğiyle elle girilebilir")}


@router.put("/matches/{match_id}/lineup", summary="İlk 11'i gir (canlı maç girdisi)")
def put_lineup(
    match_id: int,
    payload: LineupIn,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """İlk 11'i `player_appearances`'a yazar; kadro farkındalığını açar.

    Bu çağrı yapılmadan `subs_used` ve `off_prior` None kalır ve zamanlama /
    "kim çıkar" tabloları panelde sessizce devre dışıdır.
    """
    match = _match_or_404(session, match_id)
    existing = {r.player_external_id: r for r in _rows_for(session, match_id, payload.team_external_id)}
    if payload.replace:
        for r in existing.values():
            session.delete(r)
        existing = {}
    kickoff = match.kickoff or datetime.now(UTC)
    minutes = max(MIN_PLAYED_MINUTES, int(payload.minute))
    for p in payload.starters:
        row = existing.get(p.player_external_id)
        if row is None:
            row = models.PlayerAppearance(
                sport=football.SPORT_NAME, player_external_id=p.player_external_id,
                match_external_id=match_id, team_external_id=payload.team_external_id,
                kickoff=kickoff, minutes=minutes,
            )
            session.add(row)
        row.minutes = minutes
        row.substituted_in_minute = None      # ilk 11 → 0. dakikada sahada
        row.substituted_out_minute = None
        if p.position is not None:
            row.position_played = p.position
    session.commit()
    rows = _rows_for(session, match_id, payload.team_external_id)
    return {
        "match_external_id": match_id, "team_external_id": payload.team_external_id,
        "ilk11": len(payload.starters), "kayitli_oyuncu": len(rows),
        "sahada": [r.player_external_id for r in _on_pitch(rows, payload.minute)],
        "kullanilmis_hak": _subs_used(rows, payload.minute),
    }


@router.post("/matches/{match_id}/substitution", summary="Değişikliği kaydet (canlı maç girdisi)")
def post_substitution(
    match_id: int,
    payload: SubstitutionIn,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Çıkanı kapatır, gireni açar; `subs_used` böylece kendiliğinden ilerler.

    Giren oyuncunun mevkisi verilmezse çıkanınkini devralır — `coach_iq` ve
    `validate_who_prior` aynı kuralı kullanır, böylece canlı kayıt ile ölçüm
    aynı dünyayı anlatır.
    """
    _match_or_404(session, match_id)
    rows = _rows_for(session, match_id, payload.team_external_id)
    by_id = {r.player_external_id: r for r in rows}
    off = by_id.get(payload.player_off)
    if off is None:
        raise HTTPException(status_code=400,
                            detail=f"oyuncu {payload.player_off} bu maçın kadrosunda yok "
                                   f"— önce PUT /admin/matches/{match_id}/lineup")
    if off.substituted_out_minute is not None:
        raise HTTPException(status_code=409,
                            detail=f"oyuncu {payload.player_off} zaten "
                                   f"{off.substituted_out_minute:g}. dakikada çıkmış")
    if payload.player_on in by_id and by_id[payload.player_on].substituted_in_minute is not None:
        raise HTTPException(status_code=409,
                            detail=f"oyuncu {payload.player_on} zaten sahaya girmiş")

    agreement = _agreement(session, match_id, payload.team_external_id,
                           payload.minute, payload.player_off)
    _touch_minutes(rows, payload.minute)
    off.substituted_out_minute = _whole_minute(payload.minute)
    off.minutes = max(MIN_PLAYED_MINUTES,
                      int(payload.minute - float(off.substituted_in_minute or 0)))
    on = by_id.get(payload.player_on)
    if on is None:
        on = models.PlayerAppearance(
            sport=football.SPORT_NAME, player_external_id=payload.player_on,
            match_external_id=match_id, team_external_id=payload.team_external_id,
            kickoff=off.kickoff, minutes=MIN_PLAYED_MINUTES,
        )
        session.add(on)
    on.substituted_in_minute = _whole_minute(payload.minute)
    on.substituted_out_minute = None
    on.minutes = MIN_PLAYED_MINUTES
    on.position_played = payload.position or off.position_played
    session.commit()

    rows = _rows_for(session, match_id, payload.team_external_id)
    return {
        "match_external_id": match_id, "team_external_id": payload.team_external_id,
        "dakika": payload.minute, "cikan": payload.player_off, "giren": payload.player_on,
        "kullanilmis_hak": _subs_used(rows, payload.minute),
        "sahada": sorted(r.player_external_id for r in _on_pitch(rows, payload.minute)),
        "oneriyle_uyusma": agreement,
    }


@router.get("/matches/{match_id}/squad-state", summary="O dakikadaki kadro durumu")
def get_squad_state(
    match_id: int,
    team_external_id: int = Query(...),
    minute: float = Query(..., ge=0, le=130),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Panelin canlı karar çağrısına geçireceği iki sayı: sahadakiler ve kullanılmış hak.

    Boş dönerse kadro girilmemiştir ve zamanlama / "kim çıkar" tabloları o maçta
    çalışmaz — panel bunu gizlemeden göstermelidir.
    """
    _match_or_404(session, match_id)
    rows = _rows_for(session, match_id, team_external_id)
    on_pitch = _on_pitch(rows, minute)
    return {
        "match_external_id": match_id, "team_external_id": team_external_id,
        "dakika": minute,
        "kadro_girildi": bool(rows),
        "sahada": sorted(r.player_external_id for r in on_pitch),
        "kullanilmis_hak": _subs_used(rows, minute),
        "mevkiler": {r.player_external_id: r.position_played
                     for r in on_pitch if r.position_played},
        "uyari": (None if rows else
                  "kadro girilmedi — subs_used ve off_prior boş gider, zamanlama ve "
                  "'kim çıkar' tabloları bu maçta devre dışıdır"),
    }
