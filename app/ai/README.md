# ai/  [BOŞ İSKELET]

**Faz 3: Claude yorum katmanı.**

Engine'in ürettiği sayısal sonuçları teknik ekibe insan diliyle açıklar.

**Tasarım:**
- Engine sonucu (`metric + reasoning`) prompt şablonuna gömülür.
- Claude (Anthropic API) çağrılır.
- Çıktı: kısa, gerekçeli açıklama (hangi sayıya dayandığı belli).
- Token kullanımı `core/usage/` üzerinden sayılır.

**Bağımlılık yönü:** `ai/` engine'i tüketir, engine ai'yi bilmez. Tek yön.

**Şimdi:** sadece bir `Commentator` arayüzü (boş `base.py` ileride). Mantık yok.
