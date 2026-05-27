# tests/fixtures/

Gerçek API yanıtlarından alınmış örnek JSON veri setleri.

**Amaç:**
- Testler API'ye dokunmasın, hızlı çalışsın, kota yakmasın.
- Geliştirme sırasında "fixture modu" açılırsa adapter API yerine buradan okur.

**Fixture modu:** `.env` içinde `USE_FIXTURES=true` → `data/sources/api_football.py`
gerçek HTTP yerine bu klasördeki dosyaları döndürür.

**Veri:**

- `leagues.json` — Süper Lig (203) + Premier League (39, top-level kayıt)
- `teams_203.json` — Süper Lig'in 10 takımı
- `matches_<team_id>.json` — her takım için son N maç (7 FT round + 2 NS round
  düşey döngüde dağıtılır; her takım 9 maçta görünür)

**Üretim:**

```
python scripts/generate_fixtures.py
```

Deterministik (sabit seed); skorlar takım gücü + ev avantajıyla Poisson
örneklenir. **Skorlar uydurma, takım kimlikleri (Galatasaray=611 vb.) gerçek**;
2024-25 Süper Lig için "plausible" senaryo — kanonik değil. Tarih dağılımı
2024-08-17'den başlayan 7 hafta finished (FT) + 2026-06'da 2 hafta upcoming
(NS); `engine.schedule`, `engine.predict` uçlarını test etmek için yeterli.

API-Football'un ham şeması korunur (üst seviye `get/results/paging` + içte
`response[]` listesinin `fixture/league/teams/goals` alanları) — adapter
katmanı saf domain modeline çevirir.
