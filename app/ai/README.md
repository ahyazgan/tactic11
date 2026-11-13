# ai/

Yorum katmanı. Engine'in ürettiği sayısal sonucu teknik ekibe insan diliyle açıklar.

**Dosyalar:**
- `anthropic_client.py` — Anthropic API sarmalayıcısı. `ANTHROPIC_API_KEY` boşsa stub mod:
  gerçek istek atılmaz, `is_stub()` True döner. Model sabiti bu dosyadadır.
- `llm_client.py` — sağlayıcıdan bağımsız `LLMClient` arayüzü ve `get_llm_client()`.
  Bugün yalnız Anthropic uygulanmış; diğer sağlayıcılar `is_stub=True` iskeletidir.
- `prompts.py` — sabit sistem promptu (önbelleğe uygun) ve engine sonucu → prompt gövdesi.
- `commentator.py` — `Commentator` arayüzünün somut uygulaması. Anahtar yoksa belirlenimci
  stub yanıtı döner; kota `core/usage/` üzerinden sayılır.
- `base.py` — `Commentator` arayüzü.

**Tasarım:**
- Girdi her zaman engine sonucudur (`metric + reasoning`); yorum hangi sayıya dayandığını söyler.
- Yorum sayı üretmez, hesap yapmaz. Sayı engine'den gelir.

**Bağımlılık yönü:** `ai/` engine'i tüketir, engine `ai/`'yi bilmez.

**Sınır:** stub modda dönen metin gerçek model çıktısı değildir; panelde gerçek yorum
görmek için API anahtarı gerekir.
