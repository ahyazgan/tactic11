# engine/schedule/

Fikstür yoğunluğu analizi — önümüzdeki N gün içinde takımın oynayacağı
maçlardan rotasyon/yük kararına yardımcı sinyal üretir.

**Tipik üretim:**
- `upcoming_count` — ufuk içindeki maç sayısı
- `matches_next_7d`, `matches_next_14d` — pencere yoğunluğu
- `days_until_next_match` — ilk maça kalan gün
- `next_kickoffs` — yakından uzağa kickoff listesi
- `dense_schedule` — 1 haftada 3+ veya 2 haftada 5+ maç varsa True

**Diğer engine'lerle aynı kural:** girdi `Iterable[MatchLike]`, çıktı
`EngineResult[ScheduleReport]`. DB/HTTP/LLM yok.

**Bağımlı olunan:** `app.engine._protocols.MatchLike`, `app.sports.football`,
`app.audit`.

**Sonraki adımlar (opsiyonel):** rakip ratingleri için "fikstür zorluğu"
hesabı — `engine.rating`'i tüketebilir, ama bunu yapmak engine'i engine'e
bağımlı kılar; o yüzden ayrı bir `engine.fixture_difficulty` modülü olarak
düşünmek daha temiz olur.
