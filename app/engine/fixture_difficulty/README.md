# engine/fixture_difficulty/

Bir takımın önündeki rakiplerin gücünü özetler — `engine.schedule` "kaç maç"
der, bu modül "ne kadar zor" der. Rotasyon/yorgunluk kararına `schedule`'la
beraber girer: yoğun + zorlu fikstür = en yüksek alarm.

**Tipik üretim:**

- `matches_considered` — rating'i bilinen rakip maç sayısı
- `matches_unknown_opponent` — kapsam eksiği uyarısı (rating dict'te yoksa)
- `avg_opponent_rating` — düz ortalama (ağırlıksız)
- `weighted_difficulty` — zaman ağırlıklı ortalama (yakın maç yüksek ağırlık)
- `hardest_opponent_id/_rating`, `easiest_opponent_id/_rating`
- `home_match_count`, `away_match_count`

**Zaman ağırlığı:** lineer decay,
`w = max(0.2, 1 - days_until / 28)` — yakın maç ~1.0, 14 gün ~0.5,
28+ gün taban 0.2'ye iner. "Önümüzdeki haftalar" daha çok söz sahibi.

**Engine kuralı:** girdi `Iterable[MatchLike]` + önceden hesaplanmış
`dict[int, float]` (opponent_id → rating); çıktı
`EngineResult[FixtureDifficultyReport]`. DB/HTTP/LLM **yok**. Rakip
rating'ini API katmanı (veya scheduler) önceden besler.

**Bağımlılıklar:** `app.engine._protocols.MatchLike`, `app.sports.football`,
`app.audit`. `engine.rating`'e direkt import yok — engine'lerin birbirini
tüketmesinden kaçınıyoruz; rating dict'i üst katmanın sorumluluğu.

**Sınırlar:**

- Rakibin rating'i `compute_team_rating`'in son N maç penceresi; pencere
  küçükse rating gürültülü olur (`engine.rating` zaten low-sample uyarısı
  vermiyor — bu engine'in `matches_unknown_opponent` sinyali kapsam eksiği
  için var).
- Ev/dep ayrımı raporun içinde ama rating'e dahil değil (rating zaten ev/dep
  ortalaması) — gerekirse v2'de `home/away_weighted_difficulty` ayrılır.
- Yaralı oyuncular, hava durumu, motivasyon yok — model "sayısal güç" üzerine.

**Ufuk:**

- Rating'i `expected_goals_against` ile birleştir (savunma profili)
- Maç önemi ağırlığı (lig vs kupa)
- "Geçmiş benzer fikstürde nasıl yaptık" — engine.opponent'ı tüket
