"""Compliance — KVKK/sağlık verisi denetim mantığı (saf).

Oyuncu sağlık/performans verisi KVKK'da **özel nitelikli kişisel veri**. Bir
kulübe satılabilmesi için: veriyi sınıflandır + erişimi denetle + olağandışı
erişimi (olası sızıntı) tespit et.

İki saf yardımcı:
1. `classify_sensitivity` — veri kategorisini KVKK sınıfına eşler.
2. `detect_access_anomalies` — erişim kayıtlarından şüpheli toplu erişim
   (kısa sürede çok sayıda oyuncunun hassas verisi → olası ihlal) çıkarır.

Saf: erişim kaydı listesi → denetim raporu. DB/HTTP yok (kayıt persistance
çağıran tarafta).
"""
from __future__ import annotations

from dataclasses import dataclass, field

ENGINE_NAME = "engine.compliance"
ENGINE_VERSION = "1"

# KVKK özel nitelikli (sağlık vb.) sayılan veri kategorileri.
SPECIAL_CATEGORY = frozenset({
    "health", "injury", "performance_test", "wellness", "gps_load", "medical",
})
# Kişisel (özel nitelikli olmayan ama kişiye bağlı) veri.
PERSONAL_CATEGORY = frozenset({
    "contract", "salary", "player_profile", "appearance",
})

# Şüpheli toplu erişim: pencere (dk) içinde bir kullanıcı bu kadar farklı
# özne'nin hassas verisine erişirse → olası sızıntı.
BULK_WINDOW_MIN = 60.0
BULK_DISTINCT_THRESHOLD = 20


def classify_sensitivity(data_category: str) -> str:
    """KVKK sınıfı: 'ozel_nitelikli' | 'kisisel' | 'genel'."""
    cat = (data_category or "").lower()
    if cat in SPECIAL_CATEGORY:
        return "ozel_nitelikli"
    if cat in PERSONAL_CATEGORY:
        return "kisisel"
    return "genel"


@dataclass(frozen=True)
class AccessEvent:
    user_id: int
    subject_id: int           # erişilen oyuncu
    data_category: str
    minute: float             # epoch/relative dakika (sıralama için)


@dataclass(frozen=True)
class AccessAnomaly:
    user_id: int
    reason: str
    distinct_subjects: int
    window_min: float


@dataclass(frozen=True)
class AccessAuditReport:
    total_events: int
    special_category_events: int   # özel nitelikli erişim sayısı
    distinct_users: int
    anomalies: tuple[AccessAnomaly, ...] = field(default_factory=tuple)


def detect_access_anomalies(
    events: list[AccessEvent],
    *,
    window_min: float = BULK_WINDOW_MIN,
    bulk_threshold: int = BULK_DISTINCT_THRESHOLD,
) -> AccessAuditReport:
    """Erişim kayıtlarından şüpheli toplu hassas-veri erişimini tespit et."""
    special = [e for e in events if classify_sensitivity(e.data_category) == "ozel_nitelikli"]

    # Kullanıcı bazlı sliding-window: pencere içinde farklı özne sayısı.
    by_user: dict[int, list[AccessEvent]] = {}
    for e in special:
        by_user.setdefault(e.user_id, []).append(e)

    anomalies: list[AccessAnomaly] = []
    for uid, evs in by_user.items():
        evs.sort(key=lambda x: x.minute)
        left = 0
        max_distinct = 0
        for right in range(len(evs)):
            while evs[right].minute - evs[left].minute > window_min:
                left += 1
            distinct = len({evs[k].subject_id for k in range(left, right + 1)})
            max_distinct = max(max_distinct, distinct)
        if max_distinct >= bulk_threshold:
            anomalies.append(AccessAnomaly(
                user_id=uid,
                reason=(f"{int(window_min)} dk'da {max_distinct} farklı oyuncunun "
                        "özel nitelikli verisine erişim — olası sızıntı/inceleme"),
                distinct_subjects=max_distinct,
                window_min=window_min,
            ))

    return AccessAuditReport(
        total_events=len(events),
        special_category_events=len(special),
        distinct_users=len({e.user_id for e in events}),
        anomalies=tuple(anomalies),
    )
