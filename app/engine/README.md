# engine/

Hesaplama motorları. Saf fonksiyonlar: içeri veri girer, dışarı hesap çıkar.

**Kurallar (kesin):**
- API'ye, veritabanına, dil modeline doğrudan bağlanmaz.
- `domain/` modellerini tüketir.
- Çıktı "sonuç + gerekçe (kullanılan metrikler)" ikilisidir; `audit/` bunu kalıcı yazabilir.
- Motor veritabanına kendisi yazmaz; orkestrasyon yazar.

**Bağımlılık yönü:** yalnız `domain/` ve `core/`. Üstündeki `ai/`, `agents/`, `api/`
engine'i tüketir; engine onları bilmez.

**Düzen:** her motor kendi klasöründedir (bugün 129 klasör); klasör adı motorun cevapladığı
sorudur. Ana gruplar ve örnekleri:

| Grup | Örnek klasörler |
|---|---|
| Takım ve maç | `form`, `rating`, `xg`, `xt`, `ppda`, `field_tilt`, `tempo`, `transition`, `match_dominance` |
| Rakip | `opponent`, `opponent_weakness`, `style_fingerprint`, `formation_matchup`, `match_plan_builder` |
| Oyuncu | `player_form`, `player_role`, `player_similarity`, `development_curve`, `vaep` |
| Yük ve sağlık | `load`, `workload`, `gps_load`, `fatigue_signal`, `injury_risk`, `return_to_play`, `rotation_plan` |
| Duran top | `set_piece`, `set_piece_zones`, `set_piece_routine`, `set_piece_timing` |
| Canlı maç | `momentum_tracker`, `sub_timing`, `live_tactical_trigger`, `live_risk_monitor`, `opponent_reaction`, `spatial_control`, `live_matchup`, `score_time_matrix` |
| Karar zekâsı | `decision_baseline`, `decision_impact`, `decision_uplift`, `what_if`, `coach_benchmark` |
| Video sinyali | `tracking`, `tracking_signals`, `space_map`, `shape_watch` |
| Güven ve kalite | `calibration`, `confidence`, `signal_quality`, `data_quality`, `audit_quality`, `backtest` |
| Tahmin | `predict`, `predict_ml`, `score_prediction`, `season_projection` |

Tam liste için klasöre bakın; bu tablo dizin değil, yön göstericidir.

**Sınırlar:**
- Canlı motorlar bugün olay verisinden türetilen yaklaşık sinyallerle çalışır; gerçek canlı
  veri akışı geldiğinde adaptör değişir, motor değişmez.
- Bir motorun var olması, önerisinin isabetli olduğunu göstermez. Karar önerilerinin isabeti
  yalnız sahada uygulanan kararlarla ölçülebilir (`decision_uplift`).
