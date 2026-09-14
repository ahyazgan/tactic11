# Takip sürekliliği — 2026-09-14

Gündüz geliştirme etiketlerinde 7, yeni gece geliştirme etiketlerinde 2 takip
kimliği iki farklı forma rengiyle görülüyor. Bu, klip boyunca tek takım atayan
renk kümelemesinin tek başına düzeltemeyeceği kimlik karışması kanıtı; gerçek
oyuncu kimliği doğruluğu ölçümü değildir.

1. Aynı dedektör kutularını sakla; mevcut ByteTrack ayarını birebir tekrar et.
2. `lost_track_seconds` çift kare hızı ölçeklemesini ölç. Süre düzeltmesini
   geliştirme kutularında dene; daha az ID üretmek tek başına başarı sayılmaz.
3. Kamera kesmesi, tekrar ve kalibrasyon boşluğunda takip belleğini ayır;
   yeniden başlayan yerel ID'leri önceki forma geçmişiyle birleştirme.
   Hız hesabını da süreklilik sınırında kes.
4. Değişecek kod: `app/tracking/pipeline.py`, gerekirse küçük takip yardımcı
   modülü ve tekrar ölçüm scripti; regresyonlar `tests/` altında. Aynı görüntü
   kutularında forma doğrusu/yanlışı/atanamayan ve çelişkili ID sayısını raporla.
5. Süre düzeltmesi geliştirmede geçerse kod/parametre hash'lerini ve yeni kontrol
   zamanlarını incelemeden dondur. Kontrolde forma doğrusu düşmemeli, yanlış ve
   başka renk ataması artmamalı, etiketli forma kutusu kaybolmamalı. Başarısız
   deney varsayılanı değiştirmez. Kesme izolasyonu ayrıca gerçek takipçi ve
   kontrollü sentetik kamera geçişiyle sınanır.
6. Ruff, mypy, ilgili/tam testler; ölçüm raporu ve BACKLOG kaydı; otomatik PR,
   son commit'in tüm kontrolleri ve normal merge.

Eski görüntü etiketlerinin tamamı artık geliştirme verisidir. Aynı maç içindeki
yeni zamanlar bağımsız maç doğrulaması olarak sunulmayacak.
