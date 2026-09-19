# Torch dilim gruplama kontrolü

19 Eylül 2026. Bu kontrol görüntüleri açılmadan yazıldı. Önceki kimlik uzlaşısı
kontrolü bir yanlış bölünmeyle kapanmıştır; burada kimlik algoritması değiştirilmez.

Aday, Torch için gerçek örtüşmeli dilim sayısını hesaplayıp iki dengeli grup
kullanır. Açık `batch_size`, ONNX hesabı, dilim geometrisi, eşikler, model, takım,
top ve takip kuralları korunur. Geliştirmede eski gündüz kesit 3 ve gece kesit 20
kullanılır. Gün ışığı 4096×1080'de 55 dilim için eski 26 yerine 28; gece
3840×1906'da 30 dilim için eski 16 yerine 15 gerekir. Diğer çözünürlüklerde gerçek
supervision çağrı gruplarıyla geometri testleri uygulanır.

Geliştirme doğrulaması ardından aday kodu, model, kaynak, kalibrasyon ve bu plan
SHA256 ile sabitlenir. Bundan sonra ayrılmış yeni kontrol:

| Kaynak | Başlangıç | Süre |
|---|---:|---:|
| 117093 birinci yarı, gündüz | 2100 sn | 10 sn |
| 117092 birinci yarı, gece | 2700 sn | 10 sn |

Kaynaklar aynı maçların yeni zamanlarıdır; bağımsız yeni maç sayılmaz. Her kaynak
kayıpsız yeni dosyaya çıkarılır. Gerçek RF-DETR, top ROI ve varsayılan supervision
takibiyle iki kol çalışır: açık eski grup boyutu ve adayın otomatik hesabı.
Her kol aynı dedektörle iki kez ölçülür; hazırlık süresi ayrıca kaydedilir.

İki tekrar kendi içinde ve mevcut/adayı karşılaştırırken kare JSON'u birebir aynı
olmalıdır. Bu, çıktı oyuncu kutusu/kimliği/takımı, top ve olay girdileri için kesin
eşitlik kapısıdır; iyileşmiş doğruluk iddiası değildir. JSON'da yer almayan ham
ara tespitlerin bütün karelerde eşitliği iddia edilmez. Sabit üç geliştirme
karesinde ham tespit kutusu/güven/sınıf eşitliği ayrıca ölçülür.

Herhangi bir çıktı farkı, tekrar kararsızlığı, kaynak/kod hash değişimi veya hata
adayın varsayılan yapılmasını engeller. Hız her kaynakta ayrı raporlanır; ilk
çalışma ısınması ve yerel GPU değişkenliği gizlenmez. Kontrol sonrası ayar taraması
yapılıp aynı kontrolün başarı olarak sunulması yasaktır. Kontrol ancak mevcut
eşitliğin korunduğunu gösterebilir; gerçek zaman veya tüm donanımlar için hız
garantisi değildir.
