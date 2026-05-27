# engine/form/

Form analizi — son N tamamlanmış maçtaki sonuçlar, gol farkı, ev/deplasman
ayrımı, clean sheets, momentum, kalite eşikleri.

**v3 → v4 (bu modül):** opsiyonel zaman ağırlığı (`time_decay_rate`). Eski
maçlar yeni maçlardan daha az sayar; `goals_for_per_match` ve
`goals_against_per_match` zaman-ağırlıklı ortalamaya döner. Diğer alanlar
(W/D/L, points, raw totals, momentum) ham sayım kalır — momentum zaten
kendi zaman semantiğini taşıyor.

## API

```python
compute_form(team_external_id, matches, *, last_n=5, time_decay_rate=0.0)
  → EngineResult[FormReport]
```

**Girdi:** `Iterable[MatchLike]` + opsiyonel parametreler. Engine tüm
finished maçlardan team-içeren olanları seçer, kickoff'a göre yeni →
eski sırlar, ilk `last_n`'i alır.

**`time_decay_rate`:** lineer üs ağırlık `w_i = exp(-rate · days_old_i)`.
Referans zaman pencerenin EN YENİ maçının kickoff'u — deterministik,
çağrı anına bağlı değil. Tipik değerler:

| Rate | Half-life | Notlar |
|---|---|---|
| 0.0 | — | Default; uniform ağırlık (geriye uyumlu) |
| 0.0077 | ~90 gün | Hafif decay — uzun form penceresi |
| 0.023 | ~30 gün | Orta — Süper Lig'de tipik form algısı |
| 0.069 | ~10 gün | Agresif — sadece son 2-3 maçı dikkate al |

## FormReport (öne çıkanlar)

- **Sayım:** `wins/draws/losses`, `points`, `points_per_game`
- **Goller:** `goals_for/against` (raw), `goal_diff`, `goals_for_per_match`*,
  `goals_against_per_match`* (* = decay-uygulanabilir)
- **Ev/dep:** `home_wins/draws/losses`, `away_wins/draws/losses`
- **Kalite (v3):** `dominant_wins` (≥2 farkla), `close_losses` (1 farkla),
  `failed_to_score`, `scoring_rate`
- **Momentum:** `current_streak`, `current_unbeaten`, `momentum`
  (recent_ppg - older_ppg), `recent_ppg`

## Sınırlamalar

- Decay sadece per_match averages'ı etkiler — W/D/L raw kalır (asimetri kasıtlı;
  ppg yine N maç üzerinden hesaplanır)
- Rate sabit; veriye dayalı MLE öğrenme Ufuk 3'te (engine.predict gibi)
- last_n penceresi sabit; "yeterli sample" eşiği yok (engine.predict
  `low_confidence` flag'iyle bu sinyali kendisi üretir)

## Engine kuralı

- Saf hesap; DB/HTTP/LLM yok
- Aşağı doğru tüketiciler: `engine.rating`, `engine.predict`, `engine.matchup`
- AuditRecord formula'da decay aktifse formül + rate yazılı
