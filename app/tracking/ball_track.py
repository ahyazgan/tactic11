"""Takip çıktısında top: düşük güvenli adaylardan zaman tutarlı iz, sabit sahte topu at.

Dondurulmuş takip hattı her karede güveni 0,3'ü geçen en güvenli top adayını
seçer; zaman tutarlılığı yoktur. 117092 panoramasında bu seçimin dokunuş
anlarında yalnız %6,5'i gerçek topa ≤ 5 m idi (docs/TOP-TESPITI-OLAY-OLCUMU.md).
Bu modül frames JSON + `scripts.track_live_candidates` aday dosyası üzerinde
çalışır (canlı telestrasyon işçisi ve ölçüm araçları), dedektörü yeniden çalıştırmaz.

1. **Aday izi** (`track_candidates`): her segmentte sabit pikselde duran adaylar
   (ışık, çizgi kesişimi) ve işaretli saha sınırı dışındakiler atılır; kalanlardan
   fiziksel olarak bağlanabilen en yüksek puanlı yol seçilir, kısa boşluklar
   doğrusal doldurulur.
2. **Sabit sahte top** (`clean_ball`): top `static_min_s` boyunca `static_radius_m`
   içinde kalıyor ve yanında (≤ `static_no_player_m`) oyuncu yoksa sahada duran bir
   nesnedir → o kareler topsuz sayılır. Gerçek top ölü topta da durur ama o zaman
   yanında oyuncu vardır.

`recompute_actors` (aktör/sahip alanlarını yeni topa göre kurma) bir ARAÇ olarak
durur, canlı yolda ÇAĞRILMAZ: iki ön kayıtlı kontrolde telestrasyonun savunan takım
doğruluğunu düşürdü (−4,2 ve −21,7 puan) ve pas kesinliğini gündüz −8 puan bozdu
(docs/TOP-TESPITI-OLAY-OLCUMU.md §7). Telestratör sahipliği kendi kuralıyla
(topa ≤ 4 m en yakın oyuncu, kısa pencere çoğunluğu) üretilmiş kareler daha iyi.

Denenip alınmayan: topu görünmediğinde son süren oyuncunun ayağına bağlamak
(geliştirmede isabeti değiştirmedi, yanlışı artırdı).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.tracking.frames import ACTOR_RADIUS_M

PITCH_L, PITCH_W = 105.0, 68.0


@dataclass(frozen=True)
class BallTrackConfig:
    static_min_s: float = 3.0
    static_radius_m: float = 1.0
    static_no_player_m: float = 3.0


def _xy(p: dict[str, Any]) -> tuple[float, float]:
    return p["x"] / 100.0 * PITCH_L, p["y"] / 100.0 * PITCH_W


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return float(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)


def _nearest_player(frame: dict[str, Any], xy: tuple[float, float]) -> tuple[float, dict[str, Any] | None]:
    best: tuple[float, dict[str, Any] | None] = (float("inf"), None)
    for p in frame.get("players", []):
        d = _dist(_xy(p), xy)
        if d < best[0]:
            best = (d, p)
    return best


def static_runs(frames: list[dict[str, Any]], cfg: BallTrackConfig) -> list[tuple[int, int]]:
    """Topun yerinde saydığı (başlangıç, bitiş dahil) kare aralıkları — yanında oyuncu olmayanlar."""
    runs: list[tuple[int, int]] = []
    i, n = 0, len(frames)
    while i < n:
        if not frames[i].get("ball"):
            i += 1
            continue
        anchor = _xy(frames[i]["ball"])
        j, last = i, i
        while j + 1 < n:
            b = frames[j + 1].get("ball")
            if b and _dist(_xy(b), anchor) > cfg.static_radius_m:
                break
            j += 1
            if b:
                last = j
        span_s = (frames[last]["minute"] - frames[i]["minute"]) * 60.0
        if span_s >= cfg.static_min_s:
            near = sorted(_nearest_player(frames[k], _xy(frames[k]["ball"]))[0]
                          for k in range(i, last + 1) if frames[k].get("ball"))
            if near[len(near) // 2] > cfg.static_no_player_m:
                runs.append((i, last))
        i = last + 1
    return runs


def recompute_actors(frames: list[dict[str, Any]]) -> int:
    """Her karede aktörü (topa ≤ ACTOR_RADIUS_M en yakın, takımı bilinen oyuncu) ve sahip takımı yeniden kur.

    `frames.build_frame` ile aynı kural; döndürülen sayı aktörü değişen kare sayısıdır.
    """
    changed = 0
    for f in frames:
        before = next((p["player_external_id"] for p in f.get("players", []) if p.get("is_actor")), None)
        actor: dict[str, Any] | None = None
        best = ACTOR_RADIUS_M
        ball = f.get("ball")
        for p in f.get("players", []):
            p["is_actor"] = False
            if ball is None or p.get("team_external_id") is None:
                continue
            d = _dist(_xy(p), _xy(ball))
            if d < best:
                best, actor = d, p
        if actor is not None:
            actor["is_actor"] = True
        f["possession_team_external_id"] = actor["team_external_id"] if actor is not None else None
        changed += (actor["player_external_id"] if actor is not None else None) != before
    return changed


def clean_ball(frames: list[dict[str, Any]], cfg: BallTrackConfig | None = None) -> dict[str, int]:
    """`frames` (zaman sıralı, tek segment) yerinde düzeltilir; sayımları döner."""
    cfg = cfg or BallTrackConfig()
    stats = {"static_removed": 0}
    for a, b in static_runs(frames, cfg):
        for k in range(a, b + 1):
            if frames[k].get("ball"):
                frames[k]["ball"] = None
                frames[k]["ball_estimated"] = False
                stats["static_removed"] += 1
    return stats


@dataclass(frozen=True)
class CandidateTrackConfig:
    """Aday izi (`track_candidates`) ayarları; ölçüm: docs/TOP-TESPITI-OLAY-OLCUMU.md."""
    min_conf: float = 0.1          # bu güvenin altı aday sayılmaz
    conf_ref: float = 0.2          # düğüm puanı log(güven / conf_ref): üstü kazandırır
    link_bonus: float = 0.5        # öncülüne fiziksel bağlanan düğüme ek puan (tutarlılık)
    max_per_sample: int = 15
    boundary_margin_px: float = 80.0   # işaretli saha sınırının bu kadar dışı aday değil
    static_share: float = 0.5      # segment örneklerinin bu payında aynı pikselde duran aday nesnedir
    static_cell_px: float = 6.0
    max_speed_mps: float = 40.0
    speed_slack_m: float = 2.0
    max_gap_s: float = 1.5         # iki aday arası en uzun görünmezlik (bağlantı için)
    gap_penalty: float = 0.05      # atlanan örnek başına
    distance_penalty: float = 0.02  # metre başına
    restart_penalty: float = 1.2   # bağlantısız yeni iz başlatma bedeli
    interp_max_s: float = 1.0      # bağlı iki aday arası doğrusal doldurma


@dataclass(frozen=True)
class BallPoint:
    t: float               # segment içi saniye
    x: float               # metre
    y: float
    conf: float
    source: str            # "cand" | "interp"


def _cell(b: list[float], cfg: CandidateTrackConfig) -> tuple[int, int]:
    return round(b[0] / cfg.static_cell_px), round(b[1] / cfg.static_cell_px)


def _in_cells(b: list[float], cells: set[tuple[int, int]], cfg: CandidateTrackConfig) -> bool:
    cx, cy = _cell(b, cfg)
    return any((cx + dx, cy + dy) in cells for dx in (-1, 0, 1) for dy in (-1, 0, 1))


def static_cells(samples: list[dict[str, Any]], cfg: CandidateTrackConfig) -> set[tuple[int, int]]:
    """Segment boyunca hep aynı pikselde beliren adaylar (ışık, çizgi kesişimi, direk).

    Sabit kamerada gerçek top bir segmentin yarısını aynı pikselde geçirmez.
    """
    from collections import Counter  # noqa: PLC0415

    seen: Counter[tuple[int, int]] = Counter()
    for s in samples:
        seen.update({_cell(b, cfg) for b in s["balls"] if b[2] >= cfg.min_conf})
    # komşu hücrelere bölünen titreşimi de say
    spread = Counter({c: sum(seen.get((c[0] + dx, c[1] + dy), 0) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                      for c in seen})
    need = cfg.static_share * len(samples)
    return {c for c, n in spread.items() if n >= need} if samples else set()


def candidate_points(samples: list[dict[str, Any]], calib: Any, cfg: CandidateTrackConfig,
                     ) -> list[list[tuple[float, float, float]]]:
    """Örnek başına saha içi adaylar: (x m, y m, güven), güvene göre azalan."""
    from app.tracking.person_filter import annotated_boundary, inside_boundary  # noqa: PLC0415

    poly = annotated_boundary(calib)
    static = static_cells(samples, cfg)
    out: list[list[tuple[float, float, float]]] = []
    for s in samples:
        balls = sorted((b for b in s["balls"] if b[2] >= cfg.min_conf and not _in_cells(b, static, cfg)),
                       key=lambda b: -b[2])[:cfg.max_per_sample]
        if poly is not None and balls:
            keep = inside_boundary(np.array([b[:2] for b in balls]), poly, cfg.boundary_margin_px)
            balls = [b for b, k in zip(balls, keep, strict=True) if k]
        pts = []
        for u, v, c, *_ in balls:
            x, y = calib.image_to_pitch_m(u, v)
            if -5.0 <= x <= PITCH_L + 5.0 and -5.0 <= y <= PITCH_W + 5.0:
                pts.append((x, y, float(c)))
        out.append(pts)
    return out


def track_candidates(times: list[float], points: list[list[tuple[float, float, float]]],
                     cfg: CandidateTrackConfig | None = None) -> list[BallPoint | None]:
    """Örnek başına en çok bir top: fiziksel olarak bağlanabilen adaylardan en yüksek puanlı yol.

    Dinamik programlama (zaman sıralı DAG): B(k) = puan(k) + max(bağlı öncül B(i) − bedel,
    önceki en iyi − yeniden başlatma). Tek tük düşük güvenli gürültü yola girmez; tutarlı
    hareket eden düşük güvenli adaylar girer.
    """
    cfg = cfg or CandidateTrackConfig()
    nodes: list[tuple[int, float, float, float]] = []  # (örnek, x, y, güven)
    for i, pts in enumerate(points):
        nodes += [(i, x, y, c) for x, y, c in pts]
    if not nodes:
        return [None] * len(times)
    score = [float(np.log(c / cfg.conf_ref)) for *_, c in nodes]
    best = [0.0] * len(nodes)
    prev: list[int | None] = [None] * len(nodes)
    linked = [False] * len(nodes)
    by_sample: dict[int, list[int]] = {}
    for k, (i, *_rest) in enumerate(nodes):
        by_sample.setdefault(i, []).append(k)
    running_best, running_arg = 0.0, None   # örnek < i olan en iyi B (yeniden başlatma için)
    done_until = -1
    for k, (i, x, y, _c) in enumerate(nodes):
        while done_until < i - 1:
            done_until += 1
            for j in by_sample.get(done_until, []):
                if best[j] > running_best:
                    running_best, running_arg = best[j], j
        cand_val, cand_prev, cand_link = running_best - cfg.restart_penalty, running_arg, False
        if cand_val < -cfg.restart_penalty:
            cand_val, cand_prev = -cfg.restart_penalty, None
        for gap in range(1, len(times)):
            p = i - gap
            if p < 0 or times[i] - times[p] > cfg.max_gap_s:
                break
            dt = times[i] - times[p]
            for j in by_sample.get(p, []):
                _pi, px, py, _pc = nodes[j]
                d = float(np.hypot(x - px, y - py))
                if d > cfg.max_speed_mps * dt + cfg.speed_slack_m:
                    continue
                val = best[j] + cfg.link_bonus - cfg.gap_penalty * (gap - 1) - cfg.distance_penalty * d
                if val > cand_val:
                    cand_val, cand_prev, cand_link = val, j, True
        best[k] = score[k] + cand_val
        prev[k], linked[k] = cand_prev, cand_link
    top = int(np.argmax(best))
    if best[top] <= 0:
        return [None] * len(times)
    k_end: int | None = top
    path: list[tuple[int, bool]] = []
    while k_end is not None:
        path.append((k_end, linked[k_end]))
        k_end = prev[k_end]
    path.reverse()
    out: list[BallPoint | None] = [None] * len(times)
    for n, (k, is_linked) in enumerate(path):
        i, x, y, c = nodes[k]
        out[i] = BallPoint(times[i], x, y, c, "cand")
        if n and is_linked:
            j = path[n - 1][0]
            pi, px, py, _ = nodes[j]
            if times[i] - times[pi] <= cfg.interp_max_s:
                for m in range(pi + 1, i):
                    w = (times[m] - times[pi]) / (times[i] - times[pi])
                    out[m] = BallPoint(times[m], px + w * (x - px), py + w * (y - py), 0.0, "interp")
    return out


def apply_track(frames: list[dict[str, Any]], samples: list[dict[str, Any]], track: list[BallPoint | None],
                offset_s: float) -> None:
    """Kare topunu iz sonucuyla değiştir (kare zamanına en yakın örnek, yarım adım içinde)."""
    times = np.array([s["seconds"] for s in samples]) + offset_s
    step = float(np.median(np.diff(times))) if len(times) > 1 else 0.1
    for f in frames:
        t = f["minute"] * 60.0
        i = int(np.argmin(np.abs(times - t))) if len(times) else -1
        p = track[i] if i >= 0 and abs(times[i] - t) <= step / 2 + 1e-6 else None
        if p is None:
            f["ball"], f["ball_estimated"] = None, False
            f.pop("ball_source", None)
            continue
        # kare şeması 0–100 ister; saha çizgisinin hemen dışındaki top kenara çekilir
        f["ball"] = {"player_external_id": 0, "x": round(min(100.0, max(0.0, p.x / PITCH_L * 100.0)), 3),
                     "y": round(min(100.0, max(0.0, p.y / PITCH_W * 100.0)), 3), "velocity_mps": None,
                     "team_external_id": None,
                     "is_actor": False, "is_keeper": False, "identity_estimated": False}
        f["ball_estimated"] = p.source != "cand"
        f["ball_source"] = p.source


def refine_segment(frames: list[dict[str, Any]], candidates: dict[str, Any], calib: Any,
                   cand_cfg: CandidateTrackConfig | None = None, cfg: BallTrackConfig | None = None,
                   ) -> dict[str, int]:
    """Bir segmentin karelerine aday izi + sabit top temizliği uygula."""
    cand_cfg = cand_cfg or CandidateTrackConfig()
    samples = candidates["samples"]
    if not frames or not samples:
        return {"tracked": 0, "static_removed": 0}
    # İlk kare ilk örnekten yazılır (fps_out örneklemesi 0. örnekten başlar).
    offset_s = frames[0]["minute"] * 60.0 - float(samples[0]["seconds"])
    times = [float(s["seconds"]) for s in samples]
    track = track_candidates(times, candidate_points(samples, calib, cand_cfg), cand_cfg)
    apply_track(frames, samples, track, offset_s)
    stats = clean_ball(frames, cfg)
    return {"tracked": sum(p is not None for p in track), **stats}
