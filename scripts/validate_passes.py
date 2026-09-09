"""Pas çıkarımını GERÇEK yayın takip verisiyle doğrula (SkillCorner open data).

## Neden

`app/tracking/passes.py` pasları aktör değişiminden çıkarıyor. Sentetik
testler mantığı doğruluyor ama "gerçek yayında ne kadar tutuyor" sorusuna
cevap vermiyordu. SkillCorner **MIT lisanslı** olarak 10 A-League maçının
yayından çıkarılmış takip verisini açtı — kare başına sahiplik ve
`player_possession` olaylarıyla birlikte. Bu, referansı olan gerçek bir sınav.

## Veriyi indir (bir kez)

    M=2017461
    B=https://raw.githubusercontent.com/SkillCorner/opendata/master/data/matches/$M
    L=https://media.githubusercontent.com/media/SkillCorner/opendata/master/data/matches/$M
    mkdir -p data/tracking/skillcorner/$M
    curl -sL "$B/${M}_match.json"           -o data/tracking/skillcorner/$M/match.json
    curl -sL "$B/${M}_dynamic_events.csv"   -o data/tracking/skillcorner/$M/events.csv
    curl -sL "$L/${M}_tracking_extrapolated.jsonl" -o data/tracking/skillcorner/$M/tracking.jsonl

`tracking.jsonl` Git LFS'te (~85 MB) — **media.** adresinden çekilmeli, `raw.`
yalnız işaretçi döndürür.

## Kullanım

    venv\\Scripts\\python.exe -m scripts.validate_passes \\
        --dir data/tracking/skillcorner/2017461

## Nasıl okunur — TAVAN önemli

Duyarlılığı tek başına okumak yanıltıcıdır: bir pasın iki ucu da gözlenmemişse
onu bulmak İMKÂNSIZDIR. Script bu yüzden **teorik tavanı** da hesaplar
(iki ucu da gözlemli referans geçişlerin oranı) ve "tavanın ne kadarı
yakalandı"yı raporlar. Asıl not budur.

Kesinlik iki ayrı sayıyla verilir: referansta ara sahiplik gözlenmemişse
bizim A→B pasımız YANLIŞ değil, daha kaba bir tariftir; o yüzden hem birebir
hem "geçerli" oran gösterilir.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.domain.tracking import PlayerPosition, TrackingFrame
from app.tracking.passes import extract_passes

FPS = 10.0                    # SkillCorner takibi 10 fps
PITCH_L, PITCH_W = 105.0, 68.0
EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
# Eşleştirme toleransı (sn) ve ara sahiplik için bakılacak en fazla adım
MATCH_TOLERANCE_S = 3.0
MAX_SKIPPED_HOPS = 4


def _load_frames(d: Path, team_of: dict[int, int]) -> list[TrackingFrame]:
    """SkillCorner takip satırlarını TrackingFrame'e çevir.

    Koordinat: metre, orijin SANTRA (x ±52.5, y ±34) → 0-100 normalize.
    Aktör: `possession.player_id` (o karede topu tutan).
    """
    out: list[TrackingFrame] = []
    with open(d / "tracking.jsonl", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("period") is None:
                continue
            holder = (row.get("possession") or {}).get("player_id")
            players = []
            for p in row.get("player_data") or []:
                if p.get("x") is None:
                    continue
                pid = p.get("player_id")
                players.append(PlayerPosition(
                    player_external_id=int(pid) if pid else 0,
                    x=min(100.0, max(0.0, (p["x"] + PITCH_L / 2) / PITCH_L * 100.0)),
                    y=min(100.0, max(0.0, (p["y"] + PITCH_W / 2) / PITCH_W * 100.0)),
                    team_external_id=team_of.get(pid),
                    is_actor=(pid is not None and pid == holder),
                ))
            if not players:
                continue
            minute = row["frame"] / FPS / 60.0
            out.append(TrackingFrame(
                sport="football", match_external_id=0,
                timestamp=EPOCH + timedelta(seconds=minute * 60),
                period=int(row["period"]), minute=round(minute, 5),
                players=tuple(players),
                ball_estimated=not bool((row.get("ball_data") or {}).get("is_detected")),
            ))
    return out


def _possession_chain(d: Path) -> list[tuple[int, int, int]]:
    """(frame_start, frame_end, player_id) — referans sahiplik zinciri."""
    with open(d / "events.csv", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)
                if r["event_type"] == "player_possession"]
    rows.sort(key=lambda r: int(r["frame_start"]))
    return [(int(r["frame_start"]), int(r["frame_end"]), int(r["player_id"]))
            for r in rows]


def main() -> int:
    p = argparse.ArgumentParser(description="Pas çıkarımını gerçek yayınla doğrula")
    p.add_argument("--dir", required=True, help="match.json + events.csv + tracking.jsonl")
    args = p.parse_args()
    d = Path(args.dir)
    for ad in ("match.json", "events.csv", "tracking.jsonl"):
        if not (d / ad).exists():
            print(f"eksik dosya: {d / ad}\nModül docstring'indeki indirme "
                  f"komutlarını çalıştır.")
            return 1

    with open(d / "match.json", encoding="utf-8") as f:
        meta = json.load(f)
    team_of = {pl["id"]: pl["team_id"] for pl in meta["players"]}

    frames = _load_frames(d, team_of)
    chain = _possession_chain(d)
    result = extract_passes(frames)

    # Referans geçişler: ardışık ve FARKLI oyuncu.
    transitions = [(a[1], a[2], b[2]) for a, b in zip(chain, chain[1:], strict=False)
                   if a[2] != b[2]]

    # TAVAN: geçişin İKİ UCU da gözlemli olmalı.
    #
    # Yalnız çıkış ucuna bakmak tavanı şişirir (ölçüldü: %62 der, gerçeği %29):
    # alıcıyı hiç görmediysek o pası bulmak İMKÂNSIZDIR, dolayısıyla tavana
    # sayılamaz. Tavanı şişirmek kendi başarımızı olduğundan kötü gösterir.
    observed = {round(f.minute * 60.0 * FPS) for f in frames
                if any(pl.is_actor for pl in f.players)}

    def _seen(lo: int, hi: int) -> bool:
        return any(fr in observed for fr in range(lo - 5, hi + 6))

    ceiling = sum(1 for a, b in zip(chain, chain[1:], strict=False)
                  if a[2] != b[2] and _seen(a[0], a[1]) and _seen(b[0], b[1]))

    # Eşleştirme
    exact = skipped = unmatched = 0
    for pas in result.passes:
        frame = pas.minute * 60.0 * FPS
        i = next((k for k, (s, e, pid) in enumerate(chain)
                  if pid == pas.from_player_external_id
                  and s - MATCH_TOLERANCE_S * FPS <= frame <= e + MATCH_TOLERANCE_S * FPS),
                 None)
        if i is None:
            unmatched += 1
            continue
        j = next((k for k in range(i + 1, min(i + 1 + MAX_SKIPPED_HOPS, len(chain)))
                  if chain[k][2] == pas.to_player_external_id), None)
        if j is None:
            unmatched += 1
        elif j == i + 1:
            exact += 1
        else:
            skipped += 1

    n = len(result.passes)
    print("\n=== Pas Çıkarımı — Gerçek Yayın Doğrulaması ===")
    print(f"  kare                : {len(frames)}")
    print(f"  aktör oranı         : %{result.actor_ratio * 100:.0f} "
          f"(sahiplik yalnız bu kadarında biliniyor)")
    print(f"  çıkarılan pas       : {n}")
    print(f"  referans geçiş      : {len(transitions)}")
    print(f"  ├ iki ucu gözlemli  : {ceiling}  → duyarlılık TAVANI "
          f"%{100 * ceiling / max(len(transitions), 1):.0f}")
    print()
    if n:
        print(f"  birebir eşleşme     : {exact}  (%{100 * exact / n:.0f})")
        print(f"  ara sahiplik atlandı: {skipped}  (%{100 * skipped / n:.0f})")
        print(f"  karşılığı yok       : {unmatched}  (%{100 * unmatched / n:.0f})")
        print(f"  GEÇERLİ kesinlik    : %{100 * (exact + skipped) / n:.0f}")
    recall = (exact + skipped) / max(len(transitions), 1)
    print(f"  duyarlılık          : %{100 * recall:.0f}")
    if ceiling:
        print(f"  TAVANIN yakalanan   : %{100 * (exact + skipped) / ceiling:.0f}"
              f"   ← asıl not budur")
    print(f"\n  reddedilenler: {result.rejected}")
    print(f"  {result.note}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
