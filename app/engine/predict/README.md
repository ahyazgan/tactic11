# engine/predict/

**Şu an (v2):** Poisson + Dixon-Coles (1997) skor tahmini — klasik istatistik, ML değil.
**v1 → v2:** Dixon-Coles düşük-skor düzeltmesi default açıldı (ρ=-0.12).
**İleride (Ufuk 3 ML):** Time decay + opponent strength + xGBoost.

## Model

```
X ~ Poisson(λ)
λ_home = home_form.goals_for_per_match
λ_away = away_form.goals_for_per_match
P(h, a) = P_Poisson(h | λ_home) · P_Poisson(a | λ_away) · τ(h, a, λ_home, λ_away, ρ)
```

**Dixon-Coles τ düzeltmesi** — saf Poisson, 0-0/1-0/0-1/1-1 frekansını
sistematik biçimde az tahmin eder (futbol verisinde düşük-skor maçlar
arasında hafif negatif korelasyon var). DC bu dört hücreyi düzeltir:

| Hücre | τ |
|---|---|
| (0, 0) | 1 - λ_h·λ_a·ρ |
| (0, 1) | 1 + λ_h·ρ |
| (1, 0) | 1 + λ_a·ρ |
| (1, 1) | 1 - ρ |
| diğer | 1 |

ρ tipik olarak -0.18..-0.05; literatür ortası ρ=-0.12 default. **ρ=0 saf
Poisson baseline'a indirger** — karşılaştırma için.

τ değişimleri sıfır toplamlı: P(0,0)/P(1,1) artar, P(0,1)/P(1,0) eşit
miktarda azalır, toplam olasılık 1 kalır.

## API

```python
compute_predict(home_form, away_form, *, home_team_id, away_team_id, rho=-0.12)
  → EngineResult[PredictReport]
```

**Girdi:** iki takımın `FormReport`'u (engine.form'dan) + opsiyonel `rho`.

**Çıktı:**
- `expected_home_goals` (λ_home), `expected_away_goals` (λ_away)
- `prob_home_win`, `prob_draw`, `prob_away_win` — 1X2 olasılıkları
- `most_likely_score` (h, a) + `most_likely_score_prob`
- `low_confidence: bool` — `sample_size < 5` ise True
- `sample_size` — `min(home_form.matches_played, away_form.matches_played)`
- `rho_used: float` — kullanılan ρ (0.0 = saf Poisson)

## Sınırlamalar

- ρ sabit (literatür değeri). Veri biriktiğinde MLE ile öğrenmek mümkün
- Ev sahibi avantajı modele formül-içi dahil değil (form zaten home/away
  ortalaması taşıyor)
- Küçük örneklemde gürültülü → `low_confidence` flag
- Time decay yok — eski maçlar yeni maçlarla aynı ağırlıkta (Ufuk 3)
- Rakip-spesifik kalibrasyon yok (Ufuk 3)

## İleride (Ufuk 3 ML)

Gerçek veri biriktiğinde:
1. ✓ ~~Dixon-Coles düzeltmesi~~ (v2'de eklendi)
2. Time decay (eski maçlara düşük ağırlık) — `λ`'yi exponential decay'le hesaplama
3. Opponent strength (rakip defansına göre normalize)
4. ρ'yu MLE ile veriden öğren (sabit -0.12 yerine takım/lig-spesifik)
5. xGBoost veya elastic-net ile rakip-spesifik kalibrasyon
6. Sakatlık riski (oyuncu yük + maç sıklığı; `engine.load`'a bağlı)

Mevcut Poisson+DC modeli **baseline** olarak kalır; yeni modeller karşılaştırma noktası kullanır.

## Engine kuralı

- Saf hesap; DB/HTTP/LLM yok
- `engine.form.FormReport` tüketir (engine-engine bağımlılık OK: ikisi de saf)
- AuditRecord formülü tam yazılı → "neden böyle çıktı" cevaplanabilir
- Eğitim verisi (gelecekte) `snapshot/`'tan beslenir (zaman serisi)
