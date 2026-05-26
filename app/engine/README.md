# engine/

Hesaplama motoru. SAF fonksiyonlar; içeri veri girer, dışarı hesap çıkar.

**Kurallar (kesin):**
- API'ye, DB'ye, LLM'e doğrudan bağlanmaz.
- `domain/` modellerini tüketir.
- Çıktıları audit'e yazılabilecek şekilde "sonuç + gerekçe (kullanılan metrikler)"
  ikilisi olarak döndürür.

Alt klasörler:
- `form/`   — Faz 2: form/trend
- `load/`   — Faz 2: oyuncu yük/rotasyon
- `rating/` — Faz 2: takım/oyuncu rating
- `opponent/` — Faz 2: rakip örüntü analizi
- `tracking/` — Faz 6 (boş iskelet)
- `predict/`  — Ufuk 3 (boş iskelet)

**Bağımlılık yönü:** sadece `domain/` ve `core/`. Üstündeki `ai/`, `agents/`,
`api/` engine'i tüketir; engine onları bilmez.
