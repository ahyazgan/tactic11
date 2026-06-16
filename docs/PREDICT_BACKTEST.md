# Tahmin Beyni — Empirik Backtest

Predict v3 (rakip-göreli güç + ev sahibi avantajı) ve kalibrasyon T'sinin
gerçek-dünya verisindeki kazancı. Walk-forward değerlendirme: her maç için
yalnız ÖNCEKİ maçlardan form kurulur (sızıntı yok).

**Veri:** `frontend/src/lib/match-results.json` — 10.855 gerçek maç (Avrupa
ligleri, 2017+). **Harness:** `app/engine/backtest/harness.py`.

## Çalıştırma

```bash
python -m scripts.predict_backtest --all          # tüm ligler
python -m scripts.predict_backtest --comp fr.1     # tek lig
```

## Sonuçlar (tüm ligler, N=10.488 tahmin)

| model | Brier | log-loss | ECE | isabet |
|---|---|---|---|---|
| baseline (saf-atak, w=0 hfa=1) | 0.6359 | 1.0627 | 0.0791 | 46.7% |
| **v3 (rakip-göreli + ev sahibi)** | **0.6248** | **1.0493** | **0.0633** | **48.4%** |

**v3 kazancı:** log-loss **+1.26%**, Brier **+1.75%**, isabet **+1.6pp**,
ECE 0.079→0.063 (daha iyi kalibre).

**Kalibrasyon (train→test, N_test=5244):** öğrenilen T=1.54 (model hafif
aşırı-güvenli) → log-loss 1.0556 → 1.0349 (**+1.87%**).

**Birleşik (v3 + kalibrasyon):** ~%3 log-loss iyileşmesi. Futbol 1X2
tahmininde anlamlı; baseline'ın iki kör noktasını (rakip savunması + ev
sahibi avantajı) kapatır, ardından kalan aşırı-güveni düzeltir.

Ligue 1 alt-kümesinde (N=2108) yön aynı: log-loss +1.13%, Brier +1.74%,
isabet 44.8→46.5%, kalibrasyon T=1.76 ile +1.75%.

> Not: Rakamlar veri sürümüne göre küçük oynayabilir; backtest deterministiktir
> (walk-forward, sabit sıralama). Yönelim tüm dilimlerde tutarlı: v3 ≥ baseline.
