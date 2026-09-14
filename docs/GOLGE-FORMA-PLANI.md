# Gölgede forma ataması — 14 Eylül 2026

Başlangıç `46cde1c`. PR #239 kontrolleri sonrası otomatik birleştirilir;
yeni çalışma da test, PR, CI ve birleştirmeye kadar tamamlanır.

1. Geometrik GT yerine doğrudan kaynak video kutularını etiketle: segment
   0/3 geliştirme, 6/9 kontrol; her segmentin 5 ve 20. saniyesine en yakın
   önbellek karesindeki bütün kişi kutuları. Seçim tahmin/GT/hata oranından
   bağımsızdır. Belirsiz/örtüşen/forma dışı kişileri ayrı tut. Geliştirme
   ve kontrol aynı maçtan gelir; bağımsız maç genellemesi iddia edilmez.
2. Geliştirmede yalnız iki basit zaman agregasyonu karşılaştır: mevcut
   takip rengi medyanı ve en parlak dörtte birlik gözlemlerin medyanı.
   İkinci yöntem gölgeyi azaltabilir fakat mavi formanın beyaz şeritlerini
   de büyütebilir. İyileşmezse üretime alma; alternatif uydurmak için kontrol
   etiketlerine bakma. Önceki 23 yanlı örnek sadece tanı amaçlıdır.
3. Geliştirmede doğru atama artar ve yanlış atama artmazsa seçimi dondur,
   kontrol görüntülerini etiketle ve aynı kuralla karşılaştır. Kontrolde
   yanlışlar artmadan doğru atama artışı şarttır. Geçerse üretime bağla;
   geçmezse deney ve veri aracı olarak tut.
4. Regresyonlar, uygun test/lint/tip kontrolleri, görsel veri/çıktı hash'leri
   ve kapsam sınırlarıyla rapor; commit/push, PR ve yeşil CI sonrası merge.
