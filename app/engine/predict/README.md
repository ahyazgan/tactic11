# engine/predict/  [BOŞ İSKELET]

**Ufuk 3: ML tahmin modelleri.**

Planlanan modeller:
- Maç sonucu olasılığı (1X2)
- Sakatlık riski
- Oyuncu piyasa değeri tahmini

**Tasarım notu:** model eğitimi ve çıkarımı (train/infer) ayrılır. Çıkarım
fonksiyonları engine arayüzüne uyar (saf girdi → sonuç + gerekçe).
Eğitim verisi `snapshot/` üzerinden gelir (zaman içinde biriken durum kaydı).
