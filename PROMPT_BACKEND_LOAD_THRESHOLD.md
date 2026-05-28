# PROMPT — engine.load eşik parametrikleşmesi

> Dar kapsamlı tek-iş prompt'u. Tahmini 1.5-2 saatlik agent işi.
> Mevcut load akışı uçtan uca çalışıyor (engine + ingest + endpoint + 22 test);
> sadece **hardcode eşiği konfigure edilebilir hale getir**.

-----

## Bağlam (kod yazmadan oku)

1. `app/engine/load/compute.py` — `HIGH_LOAD_MINUTES_PER_WEEK = 270` modül-
   seviyesi sabit. `compute_player_load(player_external_id, appearances, *,
   window_days=14, now=None)` fonksiyonu bu sabitle `high_load` bayrağı
   üretir + audit'e `high_load_threshold_minutes_per_week` olarak kaydeder.
2. `app/api/main.py` — `GET /players/{player_id}/load?window_days=N&explain=bool`
   endpoint'i bu fonksiyonu çağırıyor. Query param `window_days` var,
   `threshold` yok.
3. `app/sports/football.py` — sport-bazlı sabitler (`SPORT_NAME`,
   `FINISHED_STATUSES` vb). Şu an load eşiği yok.
4. Test dosyaları: `tests/test_engine_load.py` (3), `tests/test_engine_load_risk.py`
   (7), `tests/test_player_appearance_ingest.py` (8), `tests/test_api_player_load.py`
   (4). Hepsi `HIGH_LOAD_MINUTES_PER_WEEK = 270` üzerine kurulu — bunları
   bozma, eşik değişince behavior aynı kalmalı (backward-compatible default).

## Sorun

Eşik 270 dk/hafta lige ve pozisyona göre değişmeli (FM mantığı: CB 300dk OK,
Bundesliga 34 maçlı sezon Süper Lig 38 maçlı sezondan farklı). Şu an caller
override edemiyor; sadece compute.py'ı düzenleyerek tüm kullanıcılarda değişir.

## Görev — kesin teslimat

### A. Sabiti `app/sports/football.py`'a taşı

- `app/sports/football.py`'a ekle:

```python
# Yük analizi — engine.load default eşiği
DEFAULT_HIGH_LOAD_MINUTES_PER_WEEK: int = 270
```

- `app/engine/load/compute.py`'da:
  - `HIGH_LOAD_MINUTES_PER_WEEK` constant'ı **silme** — backward compatibility
    için, `from app.sports.football import DEFAULT_HIGH_LOAD_MINUTES_PER_WEEK
    as HIGH_LOAD_MINUTES_PER_WEEK` re-export. Eski import path'ler kırılmasın.
  - `compute_player_load` imzasına yeni keyword-only param:
    `threshold_minutes_per_week: int | None = None`
  - Body'de: `threshold = threshold_minutes_per_week if threshold_minutes_per_week
    is not None else HIGH_LOAD_MINUTES_PER_WEEK`
  - `high_load = minutes_per_week >= threshold`
  - Audit inputs'a hem `high_load_threshold_minutes_per_week` (efektif değer)
    hem `default_threshold` (sport sabiti) yaz. Override edilip edilmediği görünsün.

### B. Endpoint'e query parametresi ekle

`app/api/main.py` → `/players/{player_id}/load`:

```python
threshold_minutes_per_week: int | None = Query(
    default=None, ge=60, le=900,
    description="Yük eşiği (dk/hafta). Boşsa football.py default'u.",
),
```

- `compute_player_load(...)` çağrısına forward et.
- Audit `explain=true` çıktısında threshold'un override mı default mı olduğu
  görünsün (zaten audit.inputs taşıyor — sadece doğru değeri taşıdığını
  doğrula).

### C. Backward compatibility doğrulama

- Mevcut 22 test (3+7+8+4) **dokunmadan** geçmeli. `python -m pytest
  tests/test_engine_load.py tests/test_engine_load_risk.py
  tests/test_api_player_load.py tests/test_player_appearance_ingest.py -q`
  hepsi yeşil.
- `from app.engine.load.compute import HIGH_LOAD_MINUTES_PER_WEEK` çalışmaya
  devam etmeli (eski public API).
- Endpoint default davranışı (param verilmezse) bit-için-bit eşit.

### D. Yeni testler (3 adet)

`tests/test_engine_load.py`'a veya yeni `tests/test_engine_load_threshold.py`'a:

1. `test_threshold_override_changes_high_load_flag` — aynı appearance
   listesi, default eşik ile `high_load=True`, override `threshold=600` ile
   `high_load=False`.
2. `test_audit_records_effective_threshold` — override edildiğinde audit'te
   threshold == override değeri görünsün.
3. `test_endpoint_threshold_param_validates` — `/players/1/load?threshold_minutes_per_week=30`
   → 422 (ge=60 sınırı); `=270` ile 200 + default davranış; `=400` ile 200 + farklı
   `high_load` bayrak.

### E. Belge

- `app/engine/load/README.md` (varsa) veya `app/engine/load/compute.py`
  docstring'ine 2 satır: "Eşik artık override edilebilir; default
  `DEFAULT_HIGH_LOAD_MINUTES_PER_WEEK` `app/sports/football.py`'da."
- ROADMAP.md'de Faz 2 load notunda "PROMPT_BACKEND_LOAD_THRESHOLD.md" satırını
  `[x]` ile işaretle (artık kapandı).

## Kapsam dışı (BU PROMPT'TA YAPILMAZ)

- Lig-bazlı override (DB'de league_settings tablosu) — şu an yok, eklenmez.
  Caller (endpoint, agent, scheduler) param geçer; üst katmanda lig
  mantığına gömülür sonra.
- Pozisyon-bazlı eşik (CB vs AM ayrımı) — `player_appearances.position`
  alanı kullanılarak farklı eşik. Bunu agent v2'de düşün.
- Yaş bazlı eşik — gerekirse Faz N'de.
- Frontend UI — bu prompt sadece backend.
- Yeni alembic migration — gerekmez (config-level değişiklik, schema'ya
  dokunmaz).

## Kabul kriterleri

- [ ] `python -m pytest tests/test_engine_load*.py tests/test_api_player_load.py
      tests/test_player_appearance_ingest.py -q` → mevcut 22 + yeni 3 = 25 yeşil
- [ ] `python -m ruff check app/engine/load app/sports/football.py app/api/main.py` clean
- [ ] `python -m mypy app/engine/load app/sports/football.py` no new errors
- [ ] `from app.engine.load.compute import HIGH_LOAD_MINUTES_PER_WEEK`
      hala çalışıyor (backward compat smoke)
- [ ] `GET /players/1/load` (param yok) → default davranış (mevcut response
      shape değişmedi)
- [ ] `GET /players/1/load?threshold_minutes_per_week=500` → audit.inputs'ta
      `high_load_threshold_minutes_per_week=500` görünüyor

## Çıktı sırası

1. Yukarıdaki 4 dosyayı (`engine/load/compute.py`, `sports/football.py`,
   `api/main.py`, ilgili test dosyası) **oku** → mevcut imzalar + sabit
   pozisyonu doğrula
2. Eklenecek/değişecek satırların listesi (kısa diff özeti)
3. Implement: A → B → D → E sırası, her bölüm sonrası test
4. Belirsizlikte AskUserQuestion

## Anti-pattern

- `compute_player_load` imzasını breaking değiştirmek
- Eski `HIGH_LOAD_MINUTES_PER_WEEK` import path'ini silmek
- Endpoint default davranışını değiştirmek (param yokken eski sonuç gelmeli)
- DB migration yazmak (gerekmez, schema değişmiyor)
- Lig/pozisyon-bazlı override eklemek (kapsam dışı, başka bir tur)
