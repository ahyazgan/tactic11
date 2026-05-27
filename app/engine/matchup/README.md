# engine/matchup/

İki takımı kıyaslayan sentez — preview brief'inin altyapısı.

**Üst katman çağrı düzeni:**
1. `compute_form(home_id, prior_matches)` → home form
2. `compute_form(away_id, prior_matches)` → away form
3. `compute_head_to_head(home_id, away_id, prior_matches)` → H2H
4. `compute_matchup(home_form.value, away_form.value, h2h.value, ...)` → kıyas

**Üretilen sinyaller** (hepsi sayı, ev sahibi perspektifi):
- `form_delta_ppg`, `form_delta_goal_diff`, `momentum_delta`, `clean_sheets_delta`
- `home_advantage_factor` — son maçlarda evde galibiyet oranı (0..1)
- `h2h_dominance` — −100..+100; pozitif=ev sahibi baskın
- `advantage_score` — sayısal kompozit (yön ipucu)

**Engine kuralı:** karar vermez ("X kazanır" yok), sadece **gözlenebilir
sayı** üretir. AI prompt'u bu sayılardan brief yazar.

**Bağımlılıklar:** `engine.form.FormReport`, `engine.opponent.HeadToHead`,
`app.audit`. Diğer engine'lerden sonuç tüketmek standart pattern — engine'ler
arası bağımlılık yön kuralını bozmaz (saf hesap → saf hesap).
