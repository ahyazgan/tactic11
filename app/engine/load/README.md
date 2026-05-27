# engine/load/

Oyuncu yük ve rotasyon analizi. Belirli bir pencere içindeki dakika +
maç sıklığı; `high_load` eşiği ile rotasyon uyarısı.

## API

```python
compute_player_load(player_external_id, appearances, *, window_days=14, now=None)
  → EngineResult[PlayerLoad]
```

**Girdi:** `Iterable[PlayerAppearance]` — bir oyuncunun maç-bazlı dakika
kayıtları (`domain.PlayerAppearance` veya DB `models.PlayerAppearance`;
ikisi de aynı alanlara sahip, duck typing).

**Çıktı (`PlayerLoad`):**

| Alan | Açıklama |
|---|---|
| `matches_in_window` | Pencere içindeki maç sayısı |
| `minutes_in_window` | Toplam dakika |
| `minutes_per_match` | Ortalama dakika/maç |
| `minutes_per_week` | `minutes_in_window / window_days * 7` |
| `high_load: bool` | `minutes_per_week >= 270` (~3 maç/hafta) → True |

## HTTP

```
GET /players/{player_id}/load?window_days=14
```

`player_appearances` tablosundan okur; tablo boşsa 404 döner.

## Veri akışı

- **Lineup adapter (Faz 6):** API-Football lineup endpoint'inden çekip
  `player_appearances` tablosunu doldurur (henüz yok)
- **Migration 0005:** tabloyu açıyor (bu PR'da eklendi)
- **Engine:** saf hesap; DB/HTTP yok

## Sınırlamalar

- High load eşiği sabit (270 dk/hafta) — pozisyon bazlı (forvet ≠ kaleci)
  ayrım yok
- Pencere uniform — son maçlar daha çok yormaz; ileride time decay
  düşünülebilir
- Sakatlık geçmişi yok — gerçek risk skoruna geçmek için medical data
  lazım (faz dışı)

## Engine kuralı

- Saf hesap; DB/HTTP/LLM yok
- AuditRecord formula tam yazılı
- AI prompt builder `app/ai/prompts.py:_build_load_prompt` mevcut
