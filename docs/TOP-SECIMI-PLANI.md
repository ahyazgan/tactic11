# Top seçimi ve kayıp temaslar — 14 Eylül 2026

Başlangıç: 4eb685b. Opus için ayrılan Karne/şekil dosyaları kapsam dışı.

1. Geliştirme olaylarını görüntüde incele; referans konum/zaman dönüşümünü
   doğrula. Gözlenmiş top etiketi gerçek top demek değildir.
2. Dedektörün tüm top adaylarını saklayan tekrar üretilebilir, DB'siz bir
   deney kur. Mevcut en yüksek güven seçimiyle süreklilik kullanan seçimi
   aynı adaylarda karşılaştır. Eksik tespiti seçim başarısı gibi gösterme.
3. Yalnız geliştirmede karar ver; dondurulmuş kontrol örneklerinde temas,
   pas eşleşmesi, kayıp gözlem ve çalışma süresini ölç. GT temas konumunu
   üretim seçicisine verme. Kabul şartı: yeni eşleşmeyen pasları artırmadan
   gözlenebilir temas/pas eşleşmesinde ilerleme.
4. Geçen düzeltmeyi üretime bağla; geçmeyen deney varsayılanı değiştirmesin.
   Sınır/durum testleri, regresyon, ruff/mypy, rapor ve commit/push.

İncelemeyle belirlenen kapsam: GSR ham görüntüsü 3840×1504, kullanılan panorama
3840×1906; bu iki piksel uzayı doğrudan kıyaslanamaz. Sağlanan 65 saha çizgisi
noktası, mevcut kalibrasyonda ayrıca ortalama 10,71 m hata gösterdi. Çizgi tabanlı
kalibrasyonla saha elemesi/takip/olay zinciri baştan ölçülecek. Renk tercihi
geliştirmede 0 seçim değiştirdi; oyuncu çevresi ROI denemesi 8 temastaki doğru
seçimi artırmadı. Bu ikisi araştırma araçları olarak kalacak.
