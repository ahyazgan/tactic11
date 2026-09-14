# Karne inceleme düzeltmeleri — 14 Eylül 2026

Başlangıç: `e0237df`, dal: `codex-work`. Kapsam: karne ölçümündeki iki
doğruluk hatası; canlı öneri motorunun davranışı değişmez.

1. `coach_benchmark/compute.py`: eğitimde hiçbir eşik %15 bayrak bütçesini
   karşılamıyorsa uygun model olmadığını açıkça taşı; uygulamada bayrak verme.
   Kontrol yarısında da bütçe yetersizse başarı hükmü verme. Yuvarlanmış
   gösterim oranlarıyla eşik kararı verme.
2. `coach_iq.py` ve `measure_shape_selectivity.py`: kullanılan oyuncu değişikliği
   sayısında aynı dakikadaki ayrı olayları koru; olay anına dayalı cetvellerde
   tekilleştirmeyi koru.
3. Regresyon testleri: eski kodda yanlış başarı üreten 1/40 örneği, bütçe sınırı,
   ayrık yarıda az bayrak, boş eğitim ve aynı dakikadaki çift değişiklik.
   Ölçüm ve karne girişlerini izole SQLite ile doğrula.
4. Eski ölçüm raporunu tarihsel olarak işaretle; düzeltme sonrası gerçek veri
   ölçümü yeniden üretilemezse önceki sayıları yeni kodun sonucu olarak sunma.
5. Hedefli testler, tam pytest, ruff ve mypy; yalnız ilgili dosyaları commit/push.

Permütasyon raporu da uygun model yokken anlamlı bir p değeri üretmemeli.
