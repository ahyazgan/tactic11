# Gündüz maçı doğrulama planı — 14 Eylül 2026

Başlangıç `974605a`; yeni kayıt SoccerTrack v2 **117093**, birinci yarı.
Kaynak: projenin yayımladığı Google Drive aynası, video
`1gPoN2h2SxEjWORK6FwKTEsCuKPylar53`; CC BY 4.0, Atom Scott ve diğerleri.

1. Kaynak kayıttan 600, 690, 780 ve 870. saniyelerde başlayan 30 saniyelik
   klipler al. Bu zamanlar takip sonuçları görülmeden seçildi. Yerel 0/3/6/9
   isimleri kullanılır; gece 117092 verileri ayrı klasörde korunur.
2. Bu maça özgü saha işaretlerini görüntü üstünde doğrula. Gece kalibrasyonu
   yeniden kullanılmaz. Piksel boyutu, saha çizgileri ve kalibrasyon hatası
   raporlanır; geçersiz geometriyle konumsal doğruluk iddia edilmez.
3. Mevcut dedektör ve takip ayarlarıyla ham renk gözlemlerini bir kez al.
   Aynı kutularda ham RGB ve üretimdeki `local_grass_v1` karşılaştırılır.
   Bu maç yeni bir dış doğrulamadır; renk yöntemi/eşikleri burada ayarlanmaz.
4. Her klibin 5/20 sn'sine en yakın örnekte tüm kişi kutularını, tahminleri
   göstermeden mavi/beyaz/başka renk/belirsiz/kişi-değil olarak etiketle. Kişi
   olmayan tespitler forma başarısına dahil edilmeden ayrıca sayılır. Segment 0 yalnız
   iki takım adını eşlemek için kullanılır; esas kontrol 3/6/9'dur.
5. Doğru, yanlış, atanamayan oyuncu, başka renge atama ve kapsama birlikte
   raporlanır. Gece ve gündüz ayrı tutulur; tek değerlendirici ve ilişkili
   karelerin sınırlılığı korunur. Gündüz kazanımı ölçülmeden iddia edilmez.
6. Tekrar üretilebilir ölçüm, kaynak hash'leri, kalibrasyon/inceleme görüntüleri
   ve anlamlı regresyonlar ekle. PR'ı son commit kontrolleri geçince birleştir.

Aktarım kısıtı (tahmin/forma etiketleri incelenmeden): 0/3/6 klipleri alındı;
9 aktarılırken resmî Drive aynası `Quota exceeded` döndürdü. Eksik 9 yerine
başka bölüm seçilmedi. İlk dış karşılaştırma 0 eşleme, 3/6 kontrol olarak
sürdürülecek; planlanan kontrolün 2/3'üne erişildiği açıkça raporlanacak.

Ölçüm sonrası uygulama kararı: dış kontrol regresyonu nedeniyle ışık
normalizasyonunun genel varsayılanını geri al. `pipeline.py`, `teams.py` ve
önbellek CLI'sında ham renk varsayılan; normalizasyon açık seçimle korunur.
Yeniden çıkarma deneyi normalizasyonu açıkça seçer. Eşik/kümeleme ayarlanmaz;
bu kontrol bundan sonraki geliştirmeler için görülmüş veridir. Varsayılan ve
açık seçenekleri gerçek toplama hattında test et; ham yöntemle takip çıktısını
üret, kaynak/etiket/sonuç kanıtını ve başarısız dış doğrulamayı yayımla.
