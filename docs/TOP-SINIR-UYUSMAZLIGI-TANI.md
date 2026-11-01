# Tüketilmiş gece kaydında top / saha sınırı uyuşmazlığı

10 Ekim 2026. Bu inceleme yalnız daha önce tüketilmiş gündüz 3 ve gece 84
ham kayıtlarını okur; yeni birleşik kimlik kontrolünü, dedektör ayarlarını
veya üretim kodunu değiştirmez. Yeni model çalıştırması değildir.

Gece önizlemesinin 9,6. saniyesindeki işaretin koordinat farkı yeniden
üretildi. Eski ham kayıtta 240. karede top merkezi `(2548,25; 1678,6875)`
pikseldir. Kaynak görüntüdeki işaretli saha sınırına uzaklığı **307,29
piksel** olmasına rağmen TPS dönüşümü bunu `(60,561; 65,629)` metreye,
yani normalize `(57,677; 96,513)` konumuna taşır. Bu değer, PR #283'ün
gerçek gece video çıktısındaki 40. kareyle tam eşleşir; 0–100 kırpması
uygulanmadan da saha içinde görünür.

| Tüketilmiş ham kesit | Top bulunan örnek | İşaretli görüntü sınırı dışında | Mevcut dönüşüm kapısınca kabul edilen dış örnek |
|---|---:|---:|---:|
| Gündüz 3 | 365 / 375 | 0 | 0 |
| Gece 84 | 375 / 375 | 375 | 375 |

Gece dış örnekleri 348 doğrudan tespit, 1 ROI ve 26 interpolasyondur.
İşaretli sınır denetimi, mevcut kişi filtresindeki aynı sınır ve 3,812
piksellik toleransla yapıldı. Gece top merkezleri x=2546–2629,5,
y=1611,219–1679,813 piksel aralığındadır. Bu kesitin gerçek video çıktısı
pas veya savunma olayı üretmedi; yanlış olay üretildiği iddia edilmez.

Kodda `_draw_pitch_lines` TPS için doğrudan işaretlenmiş görüntü sınırını
çizer. `PitchCalibration.is_on_pitch` ise yalnız dönüştürülen metre
koordinatını denetler. Bu nedenle saha dışında kalan bu görüntü bölgesi
TPS'nin dış kestirimiyle saha içine döndüğünde konum kabul edilebilir.
Örnek, iki denetimin uyuşmadığını kanıtlar; her dış gözlemin yanlış top
tespiti olduğunu veya bütün dış gözlemleri atmanın güvenli olduğunu tek
başına kanıtlamaz. Havadaki gerçek toplar ayrıca korunmalıdır.

Sonraki geliştirme için bu kesit zaten tüketilmiş bir tanı verisidir.
Görüntü sınırı desteği, saha dışı sabit nesneye kilitlenme, tespit/ROI/
interpolasyon zinciri ve havadaki gerçek toplar birlikte etiketlenmelidir.
Yeni kapı ancak gündüzdeki doğru top gözlemlerini koruyan ve geceki kaynak
hatasını doğrulayan ayrı geliştirme/kontrol çalışmasıyla kabul edilir.
Süren birleşik **kişi** kontrolünün dondurulmuş kodu bu tanı nedeniyle
değiştirilmez; top doğruluğu o kontrolün başarı ölçütü değildir.

[Kaynak hashleri ve her dış örneğin dökümü](measurements/identity-guarded-consumed-ball-boundary.json),
[çalıştırılmış tanı betiğinin birebir kopyası](measurements/identity-guarded-ball-boundary-driver.txt).
İki ham kaynak hash'i, PR #283'teki gerçek video/canlı raporunda kayıtlı
değerlerle yeniden eşleşti. Hesap `fc079c4` üretim koduyla çalıştı; tanı
çıktısı yeni bir model veya düzeltme başarısı sayılmaz.
