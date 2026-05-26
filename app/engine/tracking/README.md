# engine/tracking/  [BOŞ İSKELET]

**Faz 6: kulüp tracking verisi gelince doldurulacak.**

Tracking verisinden (oyuncu konumları, hız, pres olayları) anlamlı sinyaller
çıkaran saf algoritmalar.

Planlanan analizler:
- Yerleşim çıkarımı (defansif/ofansif düzlemde takım şekli)
- Pres yoğunluğu ve tetik noktası
- Fiziksel yük (yüksek-yoğunluklu koşu, sprint sayısı)

**Bağımlılık:** `domain/` (TrackingFrame modeli Faz 6'da eklenir).
**Beslenecek kaynak:** `data/sources/tracking.py` (Faz 6'da yazılır).
