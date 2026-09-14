# Sabit kamera sinyal kalitesi — 2026-09-14

Başlangıç: `6ca634e`, çalışma dalı `feat/sabit-kamera-sinyal-kalitesi`.
SoccerTrack 117092, 600–960 sn, yerel 990401 çıktısı: 1500 kare,
18.466 kişi/kare; bir takımda >11 kişi olan kare oranı %35.2.

Bu çalışma birimi:

1. Ham GSR etiketlerini belleği sınırlı bir araçla çıkar; takım/rol bilgisini koru.
2. Dedektörü yeniden çalıştırmadan karşılaştırabilmek için dört ayrı 30 sn
   segmentin ham takip/renk gözlemlerini önbellekle. İlk iki segment geliştirme,
   son iki segment kontrol; takım eşlemesini yalnız geliştirme verisinde seç.
3. `app/tracking/teams.py` ve gerekirse `pipeline.py` içinde hakem/kenar
   karışmasını azalt. 11 kişiye zorla kırpma yapma; GT oyuncu kaybını da ölç.
4. Aynı kayıtların paslarını gerçek olay etiketleriyle karşılaştır; savunma
   olaylarının neden eksik kaldığını raporla. Doğrulanmayan müdahaleyi gerçek
   tackle/interception olarak üretme.
5. Regresyon testleri, ruff, mypy ve pytest çalıştır; ölçüm raporunu kaydet.

GT-video zaman hizası belirsizdir. Hizalama geliştirme verisinde seçilip
kontrolde sabit tutulmalı; her kontrol karesinde en iyi eşleşmeyi aramak yasak.
Mevcut TPS bu maçtan türetilmiştir; bu deney kalibrasyonun bağımsız testi değildir.
Gerçek zaman hızlandırması ve koç karnesi bu birimin dışındadır.
