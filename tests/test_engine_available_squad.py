"""available_squad engine — sınıflama + sıralama + sayım (saf)."""

from app.engine.available_squad import compute_available_squad


def _squad():
    return [
        {"player_id": 1},                          # available
        {"player_id": 2, "injured": True},         # unavailable (sakat)
        {"player_id": 3, "suspended": True},       # unavailable (kart cezası)
        {"player_id": 4, "risk_level": "extreme"}, # doubtful
        {"player_id": 5, "risk_level": "high"},    # doubtful
    ]


def test_counts():
    rep = compute_available_squad(99, _squad()).value
    assert rep.total_squad == 5
    assert rep.available_count == 1
    assert rep.doubtful_count == 2
    assert rep.unavailable_count == 2


def test_sort_order_available_first():
    rep = compute_available_squad(99, _squad()).value
    statuses = [p.status for p in rep.players]
    assert statuses == [
        "available", "doubtful", "doubtful", "unavailable", "unavailable",
    ]


def test_reasons_for_unavailable():
    rep = compute_available_squad(99, _squad()).value
    by_id = {p.player_external_id: p for p in rep.players}
    assert by_id[2].reason == "sakat"
    assert by_id[3].reason == "kart cezası"


def test_turkish_risk_label_not_doubtful_by_default():
    """Motor 'high'/'extreme' (İngilizce) bekler; Türkçe etiket doubtful YAPMAZ.
    Uç yazılırken fiziksel risk_label → high/extreme eşlenmeli (entegrasyon notu)."""
    rep = compute_available_squad(1, [{"player_id": 9, "risk_level": "Kritik"}]).value
    assert rep.available_count == 1
    assert rep.doubtful_count == 0
