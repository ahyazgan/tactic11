"""Fiziksel test verilerinden yükleme riski skoru üretir.

DB bağımlılığı yok — sadece dict listesi alır, dataclass döner (engine katmanı
saf Python; api → ai → engine → domain bağımlılık yönüne uygun).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

# Protokol başına referans aralıkları (elit Süper Lig düzeyi).
REFERENCE = {
    "sprint_10m":      {"low": 1.90, "high": 1.70, "unit": "sn",     "lower_is_better": True},
    "sprint_30m":      {"low": 4.30, "high": 3.90, "unit": "sn",     "lower_is_better": True},
    "ttest_agility":   {"low": 11.5, "high": 9.50, "unit": "sn",     "lower_is_better": True},
    "rsa":             {"low": 4.80, "high": 4.30, "unit": "sn",     "lower_is_better": True},
    "yoyo_irl1":       {"low": 16.0, "high": 19.0, "unit": "seviye", "lower_is_better": False},
    "yoyo_irl2":       {"low": 15.0, "high": 18.0, "unit": "seviye", "lower_is_better": False},
    "cmj":             {"low": 32.0, "high": 42.0, "unit": "cm",     "lower_is_better": False},
    "sj":              {"low": 28.0, "high": 38.0, "unit": "cm",     "lower_is_better": False},
    "isokinetic_quad": {"low": 2.50, "high": 3.20, "unit": "Nm/kg",  "lower_is_better": False},
    "isokinetic_ham":  {"low": 1.50, "high": 2.00, "unit": "Nm/kg",  "lower_is_better": False},
    "vo2max":          {"low": 52.0, "high": 62.0, "unit": "ml/kg/min", "lower_is_better": False},
    "body_fat_pct":    {"low": 14.0, "high": 8.0,  "unit": "%",      "lower_is_better": True},
    "gps_total_dist":  {"low": 9000, "high": 11500, "unit": "m",     "lower_is_better": False},
    "gps_hir_dist":    {"low": 800,  "high": 1200, "unit": "m",      "lower_is_better": False},
    "gps_acc_count":   {"low": 30,   "high": 50,   "unit": "adet",   "lower_is_better": False},
}


@dataclass
class TestResult:
    protocol: str
    value: float
    unit: str
    test_date: str


@dataclass
class LoadRiskReport:
    player_id: str
    player_name: str
    risk_score: float          # 0.0 (düşük) → 1.0 (yüksek)
    risk_label: str            # "Düşük" / "Orta" / "Yüksek" / "Kritik"
    flags: list[dict]          # hangi testler neden sorunlu
    summary: str               # tek cümle TR özet
    recommendations: list[str]


def _score_single(protocol: str, value: float) -> tuple[float, str | None]:
    """Tek test için 0-1 risk skoru ve varsa bayrak mesajı."""
    ref = REFERENCE.get(protocol)
    if not ref:
        return 0.0, None

    # REFERENCE değerleri heterojen (float/str/bool) → mypy `object` görür;
    # sayısal/bool alanları açıkça daralt.
    low = cast(float, ref["low"])
    lib = cast(bool, ref["lower_is_better"])

    if lib:
        # düşük değer iyi — sprint süresi, vücut yağı
        if value > low:
            score = min((value - low) / (low * 0.15), 1.0)
            return score, f"{protocol}: {value} {ref['unit']} — referans üstü ({low})"
        return 0.0, None
    # yüksek değer iyi — YoYo, CMJ, vb.
    if value < low:
        score = min((low - value) / (low * 0.15), 1.0)
        return score, f"{protocol}: {value} {ref['unit']} — referans altı ({low})"
    return 0.0, None


# Norm dereceleri (eski batarya sistemiyle aynı sözlük) — en iyi → en kötü.
NORM_LABELS = ("elit", "iyi", "ortalama", "zayıf")


def rate_against_norms(protocol: str, value: float) -> str | None:
    """Tek ölçümü elit/iyi/ortalama/zayıf norm derecesine çevir (saf).

    REFERENCE'tan türetir: `high` = elit eşiği, `low` = kabul sınırı; aradaki
    [low, high] orta noktayla iyi/ortalama'ya bölünür, low'un kötü tarafı zayıf.
    `lower_is_better` yönünü dikkate alır. Bilinmeyen protokol → None.
    """
    ref = REFERENCE.get(protocol)
    if ref is None:
        return None
    low = cast(float, ref["low"])
    high = cast(float, ref["high"])
    lib = bool(cast(bool, ref["lower_is_better"]))
    mid = (low + high) / 2.0
    if lib:
        # düşük değer iyi: high(elit) < low(kabul)
        if value <= high:
            return "elit"
        if value <= mid:
            return "iyi"
        if value <= low:
            return "ortalama"
        return "zayıf"
    # yüksek değer iyi
    if value >= high:
        return "elit"
    if value >= mid:
        return "iyi"
    if value >= low:
        return "ortalama"
    return "zayıf"


def compute_load_risk(
    player_id: str,
    player_name: str,
    tests: list[dict[str, Any]],   # [{"protocol", "value", "unit", "test_date"}, ...]
) -> LoadRiskReport:
    """Test listesinden yükleme riski raporu üret.

    Parametreler
    ------------
    tests : [{"protocol": "sprint_10m", "value": 1.85, "unit": "sn",
              "test_date": "2026-06-01"}, ...]
    """
    if not tests:
        return LoadRiskReport(
            player_id=player_id,
            player_name=player_name,
            risk_score=0.0,
            risk_label="Veri Yok",
            flags=[],
            summary="Bu oyuncu için henüz test verisi girilmemiş.",
            recommendations=["İlk test oturumunu planlayın."],
        )

    scores: list[float] = []
    flags: list[dict] = []
    for t in tests:
        s, msg = _score_single(t["protocol"], t["value"])
        scores.append(s)
        if msg:
            flags.append({
                "protocol": t["protocol"],
                "value": t["value"],
                "unit": t.get("unit", ""),
                "message": msg,
                "test_date": str(t.get("test_date", "")),
            })

    avg = sum(scores) / len(scores)

    if avg < 0.20:
        label = "Düşük"
        summary = f"{player_name} fiziksel parametreler açısından risk altında değil."
        recs = ["Mevcut antrenman yükünü koruyun."]
    elif avg < 0.45:
        label = "Orta"
        summary = f"{player_name} bazı parametrelerde dikkat gerektiriyor."
        recs = ["Yük döngüsünü gözden geçirin.", "Bir hafta içinde re-test planlayın."]
    elif avg < 0.70:
        label = "Yüksek"
        summary = (
            f"{player_name} birden fazla kritik parametrede referans altında — "
            "yük azaltılması öneriliyor."
        )
        recs = ["Antrenman yükünü %20 kısın.", "Kondisyoner ile görüşün.", "7 gün içinde re-test."]
    else:
        label = "Kritik"
        summary = (
            f"{player_name} kritik risk seviyesinde — sahaya çıkmadan önce "
            "tıbbi değerlendirme şart."
        )
        recs = ["Spor hekimiyle acil görüşme.", "Takım antrenmanından geçici muafiyet değerlendirin."]

    return LoadRiskReport(
        player_id=player_id,
        player_name=player_name,
        risk_score=round(avg, 3),
        risk_label=label,
        flags=flags,
        summary=summary,
        recommendations=recs,
    )


# Risk label'ları (compute_load_risk ile tutarlı) — bildirim eşiği için.
CRITICAL_LABEL = "Kritik"


def format_critical_alert(report: LoadRiskReport) -> str:
    """Kritik risk için kısa, telefona uygun uyarı metni (saf)."""
    lines = [
        f"⚠️ Kritik fiziksel risk — {report.player_name}",
        report.summary,
    ]
    for f in report.flags[:5]:
        lines.append(f"• {f['message']}")
    if report.recommendations:
        lines.append("Öneri: " + report.recommendations[0])
    return "\n".join(lines)


@dataclass
class ProtocolTrend:
    protocol: str
    points: list[dict]       # [{"test_date": str, "value": float}] kronolojik
    direction: str           # "improving" | "worsening" | "stable" | "insufficient"
    slope: float             # ölçüm başına değişim (en küçük kareler eğimi)
    lower_is_better: bool


def compute_protocol_trend(
    protocol: str,
    points: list[dict[str, Any]],   # [{"test_date", "value"}], kronolojik artan
) -> ProtocolTrend:
    """Bir protokolün zaman serisinden basit eğim + yön çıkar (saf).

    Yön, protokolün 'düşük mü iyi' (lower_is_better) bilgisine göre yorumlanır:
    sprint süresi düşüyorsa 'improving', YoYo seviyesi düşüyorsa 'worsening'.
    """
    ref = REFERENCE.get(protocol)
    lib = bool(cast(bool, ref["lower_is_better"])) if ref is not None else False

    # vals'i doğrudan girdi (Any) üzerinden kur; `ordered` heterojen dict
    # olduğundan değerleri `object` çıkarsanır → float() mypy hatası verirdi.
    vals = [float(p["value"]) for p in points]
    ordered = [
        {"test_date": str(p.get("test_date", "")), "value": float(p["value"])}
        for p in points
    ]

    if len(vals) < 2:
        return ProtocolTrend(protocol, ordered, "insufficient", 0.0, lib)

    n = len(vals)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(vals) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    slope = (
        sum((xs[i] - mean_x) * (vals[i] - mean_y) for i in range(n)) / denom
        if denom
        else 0.0
    )

    # "Önemsiz" eğimi stable say (ortalamanın %1'i eşiği).
    eps = abs(mean_y) * 0.01
    if abs(slope) <= eps:
        direction = "stable"
    else:
        rising = slope > 0
        improving = (rising and not lib) or (not rising and lib)
        direction = "improving" if improving else "worsening"

    return ProtocolTrend(protocol, ordered, direction, round(slope, 4), lib)
