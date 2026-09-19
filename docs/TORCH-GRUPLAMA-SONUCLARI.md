# Torch dilim gruplama sonucu

19 Eylül 2026. Gerçek örtüşmeli dilim sayısına göre iki dengeli grup kullanmak,
yerel RF-DETR/CUDA akışında çıktı eşitliğini korudu. Geliştirmede 10 saniyelik
gündüz işleme süresi 70,88→50,73 saniye, gece 33,81→31,85 saniye oldu.
Bu sırasıyla %28,4 ve %5,8 süre azalmasıdır; gerçek zaman hedefi geçilmedi.

## Değişen hesap

4096×1080 görüntü, dört nominal sıra ve %15 örtüşmeyle gerçekten **55** dilim
üretir. Eski 26'lık gruplar 26+26+3 çalışır; sabit GPU grubunun dolgusu toplam
78 görüntülük hesap oluşturur. Yeni 28'lik gruplar 28+27 çalışır, yalnız bir
dolgu ile 56 görüntülük hesap yeterlidir. Gece 3840×1906 görüntünün 30 dilimi
16+14 yerine 15+15 işlenir. Dilimlerin kendileri ve birleştirme eşikleri aynıdır.

Yalnız Torch otomatik hesabı değişti. Açık grup boyutu, ONNX hesabı, RF-DETR
ağırlıkları, güven/NMS eşikleri, top ROI, takım ve kimlik kuralları korunur.
Dokuz çözünürlük/örtüşme kombinasyonunda gerçek supervision çağrı grupları
sınanır. Farklı cihazlarda bellek ve hız garantisi verilmez.

## Geliştirme ölçümleri

RTX 5060 Laptop, Torch 2.11.0+cu128, RF-DETR 1.10.1, supervision 0.30.2.
Kaynaklar daha önce kullanılan gündüz kesit 3 ve gece kesit 20'dir.
Her akış iki kez çalıştı. Tabloda ikinci çalışma; ilk çalışmanın başlangıç
maliyeti ayrı ham raporlarda korunur. Önizleme ve DB aktarımı dahil değildir.

| Geliştirme | Eski / yeni grup | Eski / yeni süre | Çıktı eşitliği |
|---|---:|---:|---|
| Gündüz, 10 sn | 26 / 28 | 70,88 / 50,73 sn | Dört tekrarın kare JSON'u aynı |
| Gece, 10 sn | 16 / 15 | 33,81 / 31,85 sn | Dört tekrarın kare JSON'u aynı |

Her kaynakta üç sabit karenin ham tespit kutusu, güveni ve sınıfı ayrıca iki
tekrarda karşılaştırıldı; seçilen grup boyutları birebir eşit kaldı. Gece 10'luk
alternatif grup bazı sayısal sonuçları değiştirdi ve seçilmedi. Her grup
boyutunun her ortamda eşdeğer olduğu iddia edilmez. Tam akışın bütün ham ara
tespitleri karşılaştırılmış değildir; çıktı JSON'u ve aşağıdaki olaylar sınanır.
Geliştirme akışlarında olay karşılaştırması henüz eklenmemişti.

Kanıt: [geliştirme dosyaları ve hash doğrulaması](measurements/torch-batch-development-proof.json).
Mikro deney betikleri de burada saklıdır; sonradan arşivlenen betik hashleri
bağımsız zaman damgası veya geçmiş ortamın tam kaydı olarak sunulmaz.

## Kontrol sırası ve veri hazırlama hatası

Aday kodu `154968d`, ilk karar `4f1ec8a` ile yeni görüntüler açılmadan
sabitlendi: [ilk plan](TORCH-GRUPLAMA-KONTROL-PLANI.md).
Gündüz 117093/2100–2110 saniye tamamlandı.

İlk gece başlangıcı 2700 saniye yanlış seçilmişti; kaynak 2695 saniyede biter.
261 baytlık açılmayan çıktı kare sayısı kapısında reddedildi. Bu kesitte model
çalışmadı. Hatalı karar ve dosya korunur; ilk gece kontrolü başarılı sayılmaz.

Geçerli 117092/2580–2590 saniye, görüntüleri açılmadan `bea8dce` ile ilan edildi,
`e0e06a5` ile yeniden sabitlendi. İlk adayın bütün kod hashleri korunur;
değişen yalnız gece kaynak aralığı ve bunu kaydeden ek kontrol aracıdır.
[Düzeltme protokolü](TORCH-GRUPLAMA-GECE-KONTROL-DUZELTMESI.md) ve
[ikame karar](measurements/torch-batch-night-replacement-decision.json).
Görülmüş sonuçlara göre algoritma veya eşik ayarı yapılmadı.

## Yeni kontrol sonuçları

Her kaynakta 250 kaynak karesi/10 saniye, 125 işlenen örnek ve 42 çıktı karesi
vardır. Eski ayar ve otomatik aday ikişer kez çalıştı. Her kaynakta dört
çalışmanın kare JSON'u ve üretilen olayları birebir aynı çıktı.

| Kontrol | Eski / yeni ikinci çalışma | Kare/olay eşitliği |
|---|---:|---|
| Gündüz 2100–2110 sn | 77,89 / 57,50 sn | Geçti / geçti |
| İkame gece 2580–2590 sn | 30,06 / 27,96 sn | Geçti / geçti |

Gündüz kontrolünün bir bölümü CPU uygulama testleri ve mypy ile çakıştı;
bu süreler temiz bir performans deneyi olarak kullanılmaz. Gece süre azalması
%7,0'dır. Gündüz bir tahmini pas adayı, gece sıfır olay vardı. Boş olay
listelerinin eşitliği olay doğruluğu kanıtı değildir. Savunma olayı kapsamı yoktur.
İki kontrol de aynı geliştirme maçlarının yeni zamanlarıdır; bağımsız yeni
maçlar veya insan etiketli HOTA/IDF1 değerlendirmesi değildir.

[Kontrol kanıt zinciri](measurements/torch-batch-control-proof.json),
[gündüz raporu](measurements/torch-batch-day-control-result.json),
[gece raporu](measurements/torch-batch-night-control-result.json).

## Doğrulama ve kalan iş

2.947 uygulama testi geçti, 54 atlandı. Gerçek CV ortamında dilim hesabı,
ONNX korunması ve ilk kontrol korumaları için 27 test; kaynak aralığı düzeltmesi
için ek 5 test geçti. Ruff temiz, mypy 549 kaynak dosyasında başarılı; ek
kontrol aracı da ayrı denetlendi. CI bu CV korumalarını ayrıca çalıştırır.

Bu değişiklik işlem yükünü azaltır; yanlış oyuncu birleşmesi, forma hataları,
kesitler arası kişi tanıma veya pas/savunma doğruluğunu çözmüş sayılmaz.
Önceki kimlik uzlaşısı adayının beyaz 6 numarayı yanlış bölmesi açık kalır;
`consensus` deneysel seçenektir, varsayılan takip supervision ByteTrack'tir.
