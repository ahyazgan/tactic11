# engine/predict/

**Şu an:** Poisson skor tahmini (klasik istatistik, ML değil).
**İleride (Ufuk 3 ML):** Dixon-Coles + opponent strength + xGBoost.

## Şu anki implementasyon — Poisson

100 yıllık literatüre dayalı klasik futbol modeli. Takımların gol oranı (λ)
Poisson dağılır varsayımı altında olasılık hesabı. Açıklanabilir,
audit'lenebilir, sayıyla destekli.

### API
```python
compute_predict(home_form, away_form, *, home_team_id, away_team_id)
  → EngineResult[PredictReport]
```

Girdi: iki takımın `FormReport`'u (engine.form'dan).
Çıktı:
- `expected_home_goals` (λ_home), `expected_away_goals` (λ_away)
- `prob_home_win`, `prob_draw`, `prob_away_win` — 1X2 olasılıkları
- `most_likely_score` (h, a) + `most_likely_score_prob`
- `low_confidence: bool` — `sample_size < 5` ise True
- `sample_size` — min(iki takımın form maç sayısı)

### Sınırlamalar
- Bağımsızlık varsayımı: ev/dep skorları korele değil
- Ev sahibi avantajı şu an formül-içi değil
- Küçük örneklemde gürültülü → `low_confidence` flag
- Rakip-spesifik kalibrasyon yok

## İleride (Ufuk 3 ML)
Gerçek veri biriktiğinde:
1. Dixon-Coles düzeltmesi (düşük-skor maçlar için korelasyon)
2. Time decay (eski maçlara düşük ağırlık)
3. Opponent strength (rakip defansına göre normalize)
4. xGBoost veya elastic-net ile rakip-spesifik kalibrasyon
5. Sakatlık riski (oyuncu yük + maç sıklığı; `engine.load`'a bağlı)
6. Oyuncu piyasa değeri (tracking + form + skor)

Mevcut Poisson modeli **baseline** olarak kalır; yeni modeller karşılaştırma noktası kullanır.

## Engine kuralı
- Saf hesap; DB/HTTP/LLM yok
- `engine.form.FormReport` tüketir (engine-engine bağımlılık OK: ikisi de saf)
- AuditRecord formülü tam yazılı → "neden böyle çıktı" cevaplanabilir
- Eğitim verisi (gelecekte) `snapshot/`'tan beslenir (zaman serisi)
