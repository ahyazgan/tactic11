# engine/rating/

Takım rating'i — basit, formüle dayanan, açıklanabilir.

```
rating = ppg * 50 + (goal_diff/matches) * 10
```

**v1 → v2 (bu modül):** `home_rating` + `away_rating` eklendi. Aynı formül
ev-only ve dep-only subsetlere de uygulanır. Takımların evde ve deplasmanda
farklı profil sergilemesi yaygın (ev avantajı, atmosfer, seyahat
yorgunluğu) — rotasyon ve `engine.fixture_difficulty` rakip-zorluğu
kararları için side-aware sinyal gerekiyor.

## API

```python
compute_team_rating(team_external_id, matches, *, last_n=10)
  → EngineResult[TeamRating]
```

**Girdi:** `Iterable[MatchLike]` (takımın tüm maçları; iç filtre last_n
ile pencerelendirir) + opsiyonel `last_n` (default 10).

**Çıktı (`TeamRating`):**

| Alan | Açıklama |
|---|---|
| `rating` | Overall — tüm maçlardan (mevcut, geriye uyumlu) |
| `points_per_game`, `goal_diff_per_match` | Overall formül bileşenleri |
| `matches_considered` | Overall pencerede kaç maç |
| `home_rating` | Sadece ev maçlarından; subset boşsa 0.0 |
| `away_rating` | Sadece dep maçlarından; subset boşsa 0.0 |
| `home_matches`, `away_matches` | Subset boyutları (sample uyarısı için) |

`last_n` her subset için ayrı uygulanır — yani son N ev maç + son N dep
maç. Asimetri raporda görünür.

## Sınırlamalar

- Rakip kalitesi yok — Süper Lig'de tepedeki takıma karşı 1-0'la dipten
  takıma karşı 5-0'la aynı rating'e katkı yapar. `engine.fixture_difficulty`
  rakip-spesifik analiz için bunu üst seviyede tüketir.
- "Doğru" rating değil, açıklanabilir baseline. Elo/Glicko türevi v3'te.
- Form penceresi sabit — ML-tabanlı time decay Ufuk 3'e bırakıldı
  (`engine.predict` zaten Dixon-Coles ile baseline'ı genişletiyor).

## İleride

1. Rakip-ağırlıklı rating (Elo türevi) — head-to-head'leri tüket
2. Maç önemi ağırlığı (lig vs kupa, sezon başı vs kritik haftalar)
3. ML-tabanlı kompozit (xGBoost + tracking verisi)

Mevcut formül **baseline** olarak kalır; yeni modeller karşılaştırma
noktası kullanır.

## Engine kuralı

- Saf hesap; DB/HTTP/LLM yok
- `engine.form.FormReport` üzerinden 3 ayrı form çağrısı (overall + home +
  away); form pure → engine-engine bağımlılık kuralın içinde
- AuditRecord formula'da hem overall hem subset hesabı net yazılı
