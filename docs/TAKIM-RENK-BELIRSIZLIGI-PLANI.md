# Takım renklerinin belirsizliği — 14 Eylül 2026

Başlangıç: `937c31b`, `codex-work`. Kapsam: kamera takım ataması ve canlı renk
çapası. Claude'un karne çalışması ve diğer backlog işleri kapsam dışı.

1. Aynı `signal_quality_v1` gözlemleri ve dondurulmuş +9 kare hizalamasıyla
   başlangıcı kaydet. Kontrol: 511 doğru, 119 yanlış, 16 belirsiz gözlem.
2. Tek renk/boş küme durumunda iki takım öğrenildiği varsayımını kaldır.
   İki merkez mevcut RGB toleransı (30) içinde ayırt edilemiyorsa takım
   atama; bu renkleri canlı akışa çapa yapma. Geçerli çapa sonraki belirsiz
   segmentte korunmalı. Bu koruma aynı forma renginin ışıkla çok farklı
   görünmesi sorununu tamamen çözmez.
3. Tek renk, küçük renk gürültüsü, boş küme ve belirsiz→geçerli→belirsiz canlı
   segment dizisini regresyonlarla doğrula. Önce testlerin eski kodda
   başarısız olduğunu göster.
4. Önce geliştirme segmentlerini değerlendir, sonra aynı kararı dondurulmuş
   kontrolde ölç. Doğru gözlem kaybını ayrıca raporla; belirsizleştirmeyi
   sınıflandırma başarısı gibi sunma. Her iki takımın bulunmadığı sentetik
   örneklerde kazanımı gerçek maç doğruluğundan ayrı belirt.
5. Hedefli ve tam pytest, ruff, mypy; ölçüm raporu, commit/push ve PR.
