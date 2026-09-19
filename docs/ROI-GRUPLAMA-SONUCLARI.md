# Top ROI gruplama deneyi: varsayılan kapalı

19 Eylül 2026. Ayrı tek görüntülük CUDA FP16 modeli geliştirmede hızlandı, ancak
önceden sabitlenen gündüz kontrolünde son top çıktısını değiştirdi. **Varsayılan
olarak kabul edilmedi.** Video, sıcak/izole canlı işçi ve profil aracı eski ROI
çıkarımını kullanır. Araştırma için açık `--roi-single-batch` seçeneği vardır.
PR #270 ile kabul edilmiş ana dilim gruplaması korunur.

## Gerçek çalışma ve sonuç

Aynı RF-DETR ağırlıkları, kalibrasyon ve supervision takibiyle iki kolda ikişer
çalışma yapıldı. Her kontrol 30 saniye, 750 kaynak karesi, 375 yoğun gözlem ve
125 çıktı karesidir. Yeni zaman aralıkları aynı iki maça aittir; yeni maç değildir.

| Kontrol | Eski sıcak süre | Aday sıcak süre | Son kareler | Oyuncular / olaylar |
|---|---:|---:|---|---|
| Gündüz 117093, 2220–2250 sn | 167,567 sn | 139,365 sn | 2 kare farklı | Birebir eşit |
| Gece 117092, 2640–2670 sn | 84,092 sn | 85,266 sn | Birebir eşit | Birebir eşit |

Gündüz %16,83 süre azalması; gece %1,40 süre artışı ölçüldü. Gece yalnız yedi
ROI çağrısı var; kısa aralıklarda hazırlık maliyeti ve diğer işlem maliyetleri
kazancı silebilir. Yerel RTX 5060 Laptop ölçümüdür; önizleme/DB içermez, gerçek
zaman iddiası değildir. İlk koşular ve bileşen süreleri ham raporlarda ayrı durur.

Gündüz yoğun gözlemlerde en büyük top konum farkı 0,0625 piksel, güven farkı
0,00341796875; gece 0,015625 piksel ve sıfırdır. Önceden konulan yoğun gözlem
sınırları geçildi, fakat son çıktı birebir eşitliği gündüz geçilmedi. Gündüz
97. indeksli karede top x/y ve hız, 98. karede hız değişti (1,14→1,15 ve
1,53→1,51 m/sn). Oyuncu kutuları, kimlikler, takımlar ve top varlığı/kaynağı
korundu. Beş gündüz pas adayı aynı kaldı; bu, gerçek pas doğruluğu etiketi değildir.
Her kolun yoğun gözlemleri kendi tekrarında birebir eşittir.

## Geliştirme ve uygulama sınırları

Eski 10 saniyelik iki kesitte ayrı modelle sıcak tam akış gündüz %11,20, gece
%6,05 hızlandı; yaklaşık 190 MiB ek etkin GPU belleği gerekti. Ham ROI
puanları/kutuları birebir eşit değildi. Son çıktıları ve olayları eşit olan
bu geliştirme denemeleri, yeni kontroldeki farkı geçersiz kılmaz.

Model ilk ROI ihtiyacında hazırlanır, ana model değiştirilmez. Hazırlık hatası
bir kez kaydedilir ve eski çıkarıma dönülür. CPU, ONNX, FP32, derlenmemiş ve
zaten tek görüntülük ana model yolu korunur. Deneysel seçim aynı zamanda canlı
izole alt sürece açıkça taşınır. Kullanılmadığında ikinci model hazırlanmaz.

## Kanıt ve tekrar

Plan [ROI-GRUPLAMA-KONTROL-PLANI.md](ROI-GRUPLAMA-KONTROL-PLANI.md) ve
[donmuş karar](measurements/roi-batch-frozen-decision.json) kontrol açılmadan
`7fa50fa` commit'inde sabitlendi. İki kontrol tamamlandıktan sonra yalnız
varsayılanlar kapatıldı ve seçenek açıklamaları/testler güncellendi; algoritma
ve kabul sınırları kontrol üzerinde ayarlanmadı. Tarihsel doğrulayıcı bugünkü
kaynak hashlerini bu nedenle reddeder. Kontrolü yeniden üretmek için `7fa50fa`
checkout'u, kayıtlı model/ortam/kaynaklar ve yeni çıktı dizini gerekir; eski
kanıt dosyalarının üzerine yazılmamalıdır.

- [Gündüz ham sonuç](measurements/roi-batch-control-day.json)
- [Gece ham sonuç](measurements/roi-batch-control-night.json)
- [Hash doğrulaması ve tam çıktı farkları](measurements/roi-batch-control-proof.json)
- [Geliştirme betikleri ve kanıt zinciri](measurements/roi-batch-development-proof.json)
- [Yoğun geliştirme karşılaştırması](measurements/roi-batch-dense-development.json)

Aday aşamasında tam uygulama: 2.964 başarılı, 60 atlanan test. Son varsayılan
koruması, canlı/video aktarımı ve dedektör yollarında 71 ilgili CV testi geçti;
Ruff temiz, mypy 551 kaynak dosyasında hatasız.
Kimlik doğruluğu, olay doğruluğu ve genel gerçek zaman hedefi tamamlanmış değildir.
