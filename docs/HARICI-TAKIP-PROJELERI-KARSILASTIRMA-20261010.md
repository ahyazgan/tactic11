# Manager için harici takip projeleri — 10 Ekim 2026

Bu çalışma, konuşmada önerilen 15 projenin erişim, uygulanabilirlik ve Manager görüntülerindeki ilk deney sonuçlarını bir araya getirir. Kaynak koduna erişim, model ağırlığına erişim, başarılı çalıştırma ve doğruluk üstünlüğü ayrı durumlardır. Birinin başarısı diğerini kanıtlamaz.

**Karar:** Bu turdaki yeni seçenekler arasında en yararlı geliştirme adayı, **mevcut kutu ve takım kararları + takım ile sınırlandırılmış maskesiz McByte kimlikleri** birleşimidir. İki klipte gözlenen gerileme olmadan gece aynı kişi ilişkisini 21/25'ten 23/25'e çıkardı. Gündüz etiketli kişi ilişkileri ve gözlem başına takım kararları değişmedi. Bu birleşim, bileşen sonuçları görüldükten sonra geliştirildi; bağımsız doğrulama değildir. Mevcut RF-DETR + ByteTrack üretim tabanı korunur, mevcut korumalı kimlik adayının dondurulmuş kontrolü ayrı tutulur. Yeni birleşimin o adaydan daha iyi olduğu henüz ölçülmedi.

## Erişim ve kapsam

- 15 deponun sabit commitlerinden kaynak ve belge dosyaları alındı; 3.226 dosyanın SHA-256 bütünlüğü doğrulandı. Büyük medya, veri seti ve ağırlık dosyaları kaynak arşivinden alınmadı.
- EdgeTAM, SAM2.1 Hiera Large, PnLCalib'in iki modeli ve uncertainty-jnr ViT-Small ağırlıkları resmi dağıtımlardan indirildi. Hashler kanıt paketinde bulunur.
- SAM3 kaynak kodu erişilebilir; resmi `facebook/sam3/sam3.pt` isteği **401 / GatedRepoError** verdi. Bu modeli çalıştırdığımız veya erişimi tamamladığımız iddia edilmez. Resmi model erişimi gerekir.
- SoccerMaster ve SigLIP ağırlıklarının erişilebilirliği doğrulandı; bu çalışmada indirilip çalıştırılmadı.
- Uygulama ortamına bağımlılık eklenmedi. Araştırma bağımlılıkları `.cache/external-study-20261010/site` altında tutuldu. Yeni kontrol görüntüleri açılmadı; dondurulmuş 103 kod dosyası değişmedi.

## Bütün projelerin karşılaştırması

Lisans sütunu, incelenen depodaki bildirimi aktarır; model, veri ve gömülü bağımlılıkların koşulları ayrıca geçerlidir. Kök lisansın bulunmaması, serbest kullanım izni olarak yorumlanmadı.

| Proje | Asıl katkısı | Bu çalışmadaki durum | Manager için karar | Depodaki lisans bildirimi |
|---|---|---|---|---|
| [Selective Mask Propagation](https://github.com/holma91/selective-mask-propagation) | Kararsız eşleşme aralıklarında SAM2 ile kimliği düzeltme | Kaynak, model ve birebir taban tekrar üretimi doğrulandı; gündüz deneyinde kimlik gerilemesi çıktı | Mevcut uyarlaması terfi etmedi; seçici düzeltme fikri araştırma adayı | MIT; gömülü SAM2 ayrı |
| [McByte++](https://github.com/tstanczyk95/McBytePlusPlus) | Maske, hareket ve ReID ile uzun süreli takip | Tam model kısa çalıştırma testinden geçti; uzun maskeli koşu tamamlanmadı. Maskesiz bileşen ve sınırlı birleşim ayrıca ölçüldü | Maskesiz kimlik bileşeni mevcut takım/kutu kararlarıyla sınırlandırılarak geliştirme adayı seçildi | Apache-2.0; bağımlılıklar ayrı |
| [SAM3 Ball Tracking](https://github.com/holma91/sam3-ball-tracking) | Birden çok top adayından oyundaki topu seçme | Kod incelendi; resmi model erişimi 401 ile kapalı | Top takibi için denenecek aday; yerel doğruluk henüz ölçülmedi | Uygulama MIT; Meta SAM lisansı ayrı |
| [GTATrack-STC2025](https://github.com/ron941/GTATrack-STC2025) | Deep-EIoU ardından GTA-Link ile çevrimdışı kimlik birleştirme | Kaynak ve çalıştırma kayıtları incelendi; bu paketin uçtan uca koşusu yapılmadı | Kısıtlı kimlik birleştirme referansı; otomatik tüm oyuncuları birleştirme önerilmez | Kök lisans yok; bileşen koşulları farklı |
| [SoccerMaster](https://github.com/haolinyang-hlyang/SoccerMaster) | Futbola özgü ortak görsel temsil ve çok görevli sistem | Kod incelendi, backbone erişimi doğrulandı; tam sistem çalıştırılmadı | Araştırma referansı; mevcut sistemi topluca değiştirmek için kanıt yok | Kök lisans yok; SAM2/TrackLab ve diğer bileşenler ayrı |
| [Uncertainty-aware JNR](https://github.com/lukaszgrad/uncertainty-jnr) | Forma numarası ve belirsizlik tahmini | Resmi ViT-Small model, 24 gerçek kırpımda çalıştırıldı | Tek başına kimlik bağlama için reddedildi; okunabilirlik ve çok kareli doğrulama gerekli | CC-BY-SA-4.0 |
| [PnLCalib](https://github.com/mguti97/PnLCalib) | Saha noktaları ve çizgilerinden kamera kalibrasyonu | Resmi iki modelle 12 gerçek kare; 0 kalibrasyon | Bizim panoramik görüntülerimiz için doğrudan ikame değil | GPL-2.0 |
| [PathCRF](https://github.com/hyunsungkim-ds/pathcrf) | Oyuncu yörüngelerinden top sahipliği ve olay çıkarımı | Kod, veri hazırlığı ve checkpoint yapısı incelendi; Manager üzerinde çıkarım yapılmadı | Güvenilir metrik yörüngeler sağlandıktan sonra olay katmanına aday | MPL-2.0 |
| [ELASTIC](https://github.com/hyunsungkim-ds/elastic) | Olay kayıtlarını oyuncu/top yörüngeleriyle zamanlama | Kod ve giriş koşulları incelendi; Manager senkronizasyon ölçümü yok | Doğru olay dizisi ve top yörüngesi varsa sonraki aşama | Kod MPL-2.0; benchmark CC-BY-4.0 |
| [DEFCON](https://github.com/hyunsungkim-ds/defcon) | Savunma katkısı analizi | Kod incelendi; özgün Ajax verisi herkese açık değil | Kimlik/konum/olay doğruluğundan sonra ele alınmalı | Kök lisans yok |
| [SambaGraph](https://github.com/areyesan/SambaGraph) | Futbol etkileşimlerini grafik verisine dönüştürme | Kaynak ve tamamlanmamış yayın kontrol listesi incelendi | Veri erişimi ve tekrar üretilebilirlik netleşmeden ana bağımlılık yapılmamalı | Kod MIT; veri koşulları ayrı/net değil |
| [BroadTrack](https://github.com/evs-broadcast/BroadTrack) | Yayın kamerası kalibrasyonu | Kod ve lisans incelendi; çalıştırılmadı | Ürüne kopyalanacak hazır bileşen olarak seçilmedi | Özel, ticari olmayan kurum içi araştırma koşulları |
| [Jersey Number Pipeline](https://github.com/mkoshkina/jersey-number-pipeline) | Okunabilirlik filtresi ve tracklet numara okuma | Kod incelendi; yeni bir model koşusu yapılmadı | Çok kareli doğrulama yaklaşımı yararlı; doğrudan ürün bağımlılığı seçilmedi | CC-BY-NC-3.0 |
| [Roboflow Sports](https://github.com/roboflow/sports) | Takım ayrımı, saha ve spor uygulama örnekleri | SigLIP → UMAP → KMeans takım sınıflandırıcısı incelendi | Takım rengi/özelliği yardımcı sinyalidir; kalıcı oyuncu kimliği değildir | Kod MIT; model/veri koşulları ayrı |
| [TrackNet Series PyTorch](https://github.com/AnInsomniacy/tracknet-series-pytorch) | Küçük top/nesne ısı haritası modelleri | Kod ve eğitim protokolü incelendi; varsayılan veri badminton | Futbol için yeniden veri/eğitim/değerlendirme gerekir | Kök lisans yok |

## Gerçek görüntü deneyleri

Deneyler önceden görülen geliştirme verilerindedir: gündüz `seg_0003`, gece eski kontrol `seg_0040`. Eski kontrol artık geliştirme verisidir. Yeni dondurulmuş kontrolün dört klibi bu seçim için kullanılmadı. Örnek sayıları küçük olduğundan tüm maç doğruluğu, HOTA veya IDF1 sonucu çıkarılmaz.

### Forma numarası

24 kırpım, mevcut takım etiketleri arasından sıraya göre seçildi: 12 gündüz, 12 gece. Model skoruna göre örnek seçilmedi. Resmi küçük modelin ağırlıkları eksiksiz/strict yüklendi; özgün gövde kırpma ve normalizasyon kullanıldı. CPU float32 uygulaması, orijinal CUDA float16 deneyinin hız karşılaştırması değildir.

22 örnekte çıktı neredeyse tekdüze ve belirsizlik yüksek kaldı. `night_18.png` üzerindeki görsel incelemede **6** okunan numaraya model **15**, yaklaşık **%99,33** olasılık verdi. Bu tek örnek, düşük model belirsizliğinin doğru kimliği garanti etmediğini gösterir. Bu yüzde, modelin çıktısıdır; ölçülmüş doğruluk değildir.

Gündüz `day_05.png` ilk görsel notta 16 olarak yazılmıştı; küçük görüntüde 15/16 ayrımı tartışmalı olduğundan kesin doğruluk hesabına alınmadı. 24 görüntünün tümünde güvenilir numara etiketi bulunmadığı için toplu numara doğruluğu yayımlanmadı. Görsel notlar çıktı açılmadan önce, fakat model işi başlatıldıktan sonra kaydedildi; deney ön kayıtlı değildir.

### Kalibrasyon

PnLCalib `SV_kp` ve `SV_lines` modelleri, özgün 960×540 giriş dönüşümü ve önerilen eşiklerle çalıştırıldı. Her iki klipte kaynak kareleri 0, 124, 240, 374, 500 ve 686 seçildi. Seri çalışan tamamlanmış koşuda **12/12 kare işlendi, 0/12 kalibrasyon bulundu**. İlk eşzamanlı denemenin bellek hatası bu doğruluk sonucuna dahil edilmedi.

Bu sonuç, modelin her tür futbolda başarısız olduğu anlamına gelmez. Bu kontrol noktasının ve tek kamera modelinin mevcut panoramik görüntülerimize doğrudan uyum sağlamadığını gösterir. Mevcut saha geometrisi problemi ayrıca çözülmelidir; yeni kalibratör adını eklemek çözüm değildir.

### McByte++

Gerçek tespit kutuları, özgün görüntüler ve mevcut ReID ağırlığı kullanıldı. Beş karelik çalıştırma testi tamamlandı; ortak saha/kişi filtresinden sonra 100 gözlem üretildi. Bu kısa test doğruluk üstünlüğü kanıtlamaz. Maske/takip/ReID bölümü yaklaşık 21,98 saniye sürdü; dedektör dahil değildir ve canlı FPS karşılaştırması değildir.

Tam 375 örnekli gündüz koşusu bir denemede bellek tahsis hatası verdi; ikinci deneme artan bellek baskısında durduruldu. Tam koşunun doğruluk sonucu yoktur. CPU video/durum aktarımı, önbellekli kare okuma ve yerel NumPy IoU uyumluluğu kullanıldığı için sonuçlar bu açıkça belgelenen Windows uyarlamasına aittir. Kaynak projeyi tüm donanımlarda başarısız ilan etmek için yeterli değildir.

Maskeyi kapatan ayrı bileşen çıkarma deneyinde gündüz 375 örnek tamamlandı. Bu sonuç **tam McByte++ sonucu değildir**. Ana kişi ilişkilerindeki 4/8 aynı ve 1/4 farklı kişi doğruluğu değişmedi. Eski kontrolün geliştirmeye alınmış alt kümesinde aynı kişi 28/39 → 29/39, farklı kişi 27/39 → 28/39 oldu; fakat doğru takım etiketi 104 → 103, atanmayan takım 0 → 3, takım dışı sınıfın takıma atanması 6 → 12 oldu. Bu yüzden bu sürüm de terfi etmedi. Takip/ReID bölümü yaklaşık 12,88 saniyedir; dedektör/çözümleme dahil değildir.

Gece maskesiz koşuda da 375 örnek tamamlandı. Aynı kişi ilişkileri 21/25 → 24/25, farklı kişi ilişkileri 23/25 → 24/25 ve kapsanan gözlemler 57 → 58 oldu. Ancak doğru takım etiketi 21 → 20, yanlış takım etiketi 5 → 6 değişti. Takip/ReID bölümü yaklaşık 32,16 saniye sürdü. Bu bağımsız bileşen haliyle kalite koşullarını geçmedi.

### Seçici maske ve kimlik karşılaştırması

SMP, Manager'ın mevcut ByteTrack çıktısı üzerine uygulanır; özgün projenin Deep-EIoU tabanı üzerinde alınan makale sonucu ile aynı deney değildir. Eşleşme maliyetlerinin gerçek sütun marjları kaydedildi. Kayıt işleminin kişi kutularını ve renk geçmişlerini değiştirmediği birebir doğrulandı. Gündüz klibinde 53 aday pencere bulundu; çalışma 49 pencere ve 12 kimlik yeniden adlandırma olayı üretti. Maske/düzeltme bölümü yaklaşık 226,13 saniye sürdü; bu uçtan uca video işleme süresi değildir.

Gündüz `identity-person-development-labels` alt kümesinde:

| Ölçüm | Mevcut taban | SMP uyarlaması |
|---|---:|---:|
| Aynı kişi ilişkisi doğru | 4 / 8 | 3 / 8 |
| Farklı kişi ilişkisi doğru | 1 / 4 | 2 / 4 |
| Yanlış bölünme | 4 | 5 |
| Yanlış birleşme | 3 | 2 |
| Kapsanan etiketli gözlem | 14 | 14 |

Bir hatayı düzeltirken önceden doğru `3-440-d10 → 3-460-d10` ilişkisini bozdu. Takım etiketlerinde doğru sayısı 104'ten 105'e çıksa da atanmayan etiket 0'dan 1'e yükseldi. Ayrı, daha geniş eski kontrol ilişkilerinde aynı kişi 28/39 ve farklı kişi 27/39 sonuçları değişmedi. Farklı etiket dosyaları birbirini tekrar edebildiğinden bu sayılar birleştirilmez.

Özgün `benchmark` birleştirme yolu ayrıca 74 adet kaynak tespitine karşılık gelmeyen maske kutusu üretti. Bunlar son puanlama girdisinden çıkarıldı ve ayrı kaydedildi. Bu durum kendi başına kaynak kanıtı koşulunu geçersiz kılar. İlk koşu bu kontrolde durdu; sonraki koşu ihlalleri kaydedip kalan gerçek kutuları puanladı. **Gündüz denemesi terfi koşullarını geçmedi.**

Gece denemesi ilerleme kaydında 199/328 yayılım adımından sonra `CUDA error: resource already mapped` ile durdu. Aynı sırada Windows tarafında da bellek tahsis baskısı gözlendi. Bu uyarlamadaki kesin kök neden ayrıştırılmadı; bu klip için tamamlanmış tahmin veya doğruluk puanı yoktur. Yarım koşu başarı olarak sayılmadı.

Tamamlanan ölçümlerin kararları ve örnek bazında gerilemeleri [comparison-scores.json](measurements/external-tracking-20261010/comparison-scores.json) dosyasına yazılır. Eksik/tamamlanmamış koşular başarılı sonuç olarak sayılmaz. Ortak filtreler ve gerçek kaynak kutuları korunur; maske tahmininden yeni bir kutu üretip tespit yapılmış gibi sayılmaz.

### Ölçülen birleşim: mevcut takım/kutu kararları + McByte kimliği

Bileşen sonuçlarından sonra tek bir ek aday kuruldu. Mevcut ByteTrack tabanının gözlem listesi, kutuları, güven skorları ve her gözlemdeki takım değeri birebir korunur. McByte'ın aynı kaynak kutusundaki kimliği yalnızca mevcut takım değeri biliniyorsa kullanılır; kimlikler takım değerine göre ayrı tutulur. Takım bilinmiyorsa veya karşılık gelen kutu yoksa mevcut takip kimliği kullanılır. Tek karede iki gözlemin aynı kimliği alması reddedilir. Etiketler kimlik atama kuralına girdi olarak verilmez.

Toplam **15.279 gözlemde** kutu/güven ve takım değerlerinin eşitliği doğrulandı: gündüz 8.828, gece 6.451. Bu, algoritmanın bilinçli koruma özelliğidir; bağımsız takım doğruluğu kazanımı değildir. Mevcut hatalı takım kararları da korunabilir.

| Gece eski kontrol, artık geliştirme alt kümesi | Mevcut taban | Sınırlı birleşim |
|---|---:|---:|
| Aynı kişi ilişkisi doğru | 21 / 25 | **23 / 25** |
| Farklı kişi ilişkisi doğru | 23 / 25 | 23 / 25 |
| Yanlış bölünme | 2 | **0** |
| Kapsanan etiketli gözlem | 57 | 57 |
| Doğru / yanlış / atanmayan takım | 21 / 5 / 2 | 21 / 5 / 2 |

Gündüz etiketli kimlik ilişkilerinde ilerleme veya gerileme yoktur; gece iki yanlış bölünme düzelir. İki klip birlikte değerlendirildiğinde mevcut doğru ilişkilerin hiçbirini bozmadığı ve bir klipte iyileştiği için **bu sınırlı geliştirme karşılaştırmasını geçer**. Her klipte ayrı ilerleme şart değildir: gündüz tek başına iyileşme puanı almaz.

Gündüzde çelişkili görsel takım etiketleri içeren takip parçalarının sayısı ayrıca 4'ten 2'ye indi. Kimlik grupları değiştiği için bu sayı değişebilir; gözlem başına takım kararlarının değiştiği veya tek başına kimlik doğruluğunun arttığı anlamına gelmez.

Bu sonuç, iki klip üzerinde sonradan oluşturulmuş bir araştırma adayına aittir. Tüm maçlarda veya mevcut korumalı kimlik adayına karşı üstünlük kanıtı değildir. Devam yolu, önceden tüketilmiş 19 klipte mevcut korumalı adayla karşılaştırmak, kararı dondurmak ve ona ait ayrı bir kontrol protokolü uygulamaktır. Bu rapor mevcut dondurulmuş kontrolün adayını değiştirmez.

## Birleştirilecek sistemin sınırları

1. **Tespit ve kısa süreli takip:** RF-DETR + mevcut ByteTrack, sabit kaynak kutuları ve saha/kişi filtreleri.
2. **Kalıcı kimlik:** Mevcut korumalı kimlik adayının ayrı kontrolü sürer. Bu turda ölçülen takım ile sınırlandırılmış McByte birleşimi, sonraki geliştirme karşılaştırmasının adayıdır. Takım rengi tek başına kişi kimliği değildir; zamansal birlikte görünme ve hareket tutarlılığı da gerekir.
3. **Numara:** Okunabilir karelerden birden fazla zaman örneği toplanır. Çelişkili/okunamayan çıktı bilinmiyor olarak kalır. Tek yüksek model skoru kimlik birleştirmez.
4. **Top ve saha:** Oyundaki top seçimi için SAM3 gelecekte karşılaştırılabilir; önce resmi model erişimi ve aynı futbol görüntülerinde kanıt gerekir. Görüntü sınırı ile saha koordinatı tutarlılığı ayrıca korunmalıdır.
5. **Olaylar:** PathCRF bir çıkarım adayı, ELASTIC zaman eşleme adayıdır. Güvenilmez kimlik ve konumlar bu katmana aktarılıp kesin pas/oyuncu istatistiğine dönüştürülmemelidir.

Bu, modüllerin görevlerini birleştiren, küçük ölçekte çalıştırılmış bir araştırma kararıdır; 15 modelin tamamının üretime entegre edildiği anlamına gelmez. Bu değişiklik araştırma raporu, sürücü kopyaları ve kanıtları kaydeder.

## Kanıtlar ve tekrar üretim

[Kanıt dizini](measurements/external-tracking-20261010/) sabit commitleri, model hashlerini, gerçek çıktıları, hata kayıtlarını ve deney sürücülerinin metin kopyalarını içerir. Büyük model dosyaları, dış projelerin kaynakları ve maç videoları Git'e eklenmez. Yerel çalışma dizini `.cache/external-study-20261010/` altında korunur.

Kaynak/model edinme işlemleri ağ erişimi gerektirir. Deneyler repo kökünde `venv-cv` ile, ek paketler yalnızca araştırma `site` dizininde olacak şekilde çalıştırıldı. Çalıştırılabilir uygulama bağımlılıkları ve dondurulmuş kontrol kodu değiştirilmedi. NumPy IoU uyarlaması analitik köşe durumları ve 10.000 bağımsız skaler hesapla doğrulandı; yerel Cython ikilisiyle eşdeğerlik testi yapılmadı.
