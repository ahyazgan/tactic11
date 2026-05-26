# agents/  [BOŞ İSKELET]

**Ufuk 3: otomasyon / ajan katmanı.**

Planlanan ajanlar:
- Otomatik maç-öncesi raporu hazırlayan ajan
- Sürekli scout taraması (kriter eşleştiğinde uyarı)
- Sakatlık/form değişiklik uyarıları

**Tetikleyici:** `scheduler/` ajanları zamanlanmış olarak çalıştırır.
**Veri kaynağı:** `engine/` çıktıları + `ai/` yorumu.

**Şimdi:** sadece `Agent` arayüzü iskeleti. Mantık yok.
