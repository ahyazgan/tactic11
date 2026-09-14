# Video olayları — derinlemesine çalışma, 14 Eylül 2026

Başlangıç ad8da25. Çalışma kapsamı: top gözlemi, pas ve savunma olayı çıkarımı,
video/canlı JSON ve ingest zinciri, gerçek etiketli ölçüm ve regresyon testleri.

1. SoccerTrack'teki pas türü olaylar için zaman, top/aktör gözlemi, tutuş
   kararlılığı, takım belirsizliği ve çıkarılmış olay eşleşmesini raporla.
   600–780 sn geliştirme; 780–960 sn kontrol. Eşikleri kontrolde ayarlama.
   Ayrıntılı player-nodes dosyası 68 pas/orta, kompakt 12-sınıf dosyası 70
   olay içeriyor; farklı sözlükler birleştirilip tek referans sayılmayacak.
2. Olayları görüntüleme için seyreltilmiş karelerden çıkarma kaybını ölç.
   Zaten hesaplanan yüksek frekanslı takip gözlemlerini olay hattına bağla;
   yeniden dedektör çalıştırmadan hızlı temasları koru.
   Ölçüm kararı: yoğun olay akışı kontrolü geçemedi, `--dense-events` ile deneysel.
3. Pas durum makinesinde zaman/yarı/maç sınırlarını, gözlenmeyen topu,
   enterpolasyon etiketini ve aday/son sahiplik zamanlarını düzelt. Yanlış
   pozitif üretecek tek kareli temas gevşetmelerini kontrol verisiz açma.
4. Savunmada yalnız gözlenmiş sahiplik değişiminden top kazanımı çıkar;
   müdahale/pas kesme türünü kanıt yokken tahmin etme. Tahmini/provenans
   bilgisi JSON→DB→domain boyunca korunmalı; eksik savunma örneklerini tam
   savunma kapsamı gibi kullanıp güçlü taktik kıyas üretme.
5. Top enterpolasyonunda gerçek zaman, kalibrasyon sürekliliği ve fiziksel
   hız sınırını uygula. Eksik top gözlemini gerçek gözlem diye sayma.
6. Aynı önbellekte önce/sonra + SkillCorner dış kaynak regresyon ölçümü;
   bir olayı iki kez doğru saymayan eşleme. Bağımsız top/alıcı etiketi yoksa
   kesinlik iddiası yerine açık ölçüm sınırı ve olay bazlı tanı ver.
7. Hedefli testler, tüm pytest, ruff, mypy; rapor, commit ve yetkili depoya push.

Yerel eski maç verisi ölçüm kanıtıdır; yeniden ingest edilerek üzerine yazılmaz.
Yeni olay çıktıları ayrı deney klasörüne, DB zinciri testi izole SQLite'a gider.
