# Kimlik geçişi hata denetimi

Kapsam: Deep OC-SORT entegrasyonunda kaybedilen iki gündüz bağlantısının
ilk ayrışma karesini, kaynak tespitlerini ve takip kararını yeniden üretmek.
Üretim kodu, eski deneyler ve etiketler değiştirilmez. Bu çalışma yeni bir
geliştirme denetimidir; 2400–2430 / 2460–2490 kontrol kesitleri açılmaz.

1. Kaynak görüntüde 0/280→310 beyaz koşucu ve 3/440→460 mavi koşucu izlenir.
2. Tam geçmişten oynatılan tespitler ve ilk eşleştirme matrisi kaydedilir.
   Görünüş kapalı kolun da hatayı yapması modelin tek neden olmadığını sınar.
3. Beyaz koşucunun parçalı tespiti (0/298 raw 18) ve mavi oyuncu/hakem
   temasındaki karışık alt-gövde tespiti (3/458 raw 24) yalnız tanı amaçlı ayrı
   kopyada çıkarılır. İkinci kutunun tek kişiye ait olduğu kesin değildir. Bu bir oracle deneyidir;
   kare/etiket bilen bu müdahale otomatik filtre veya doğruluk kazanımı değildir.
4. Tek geliştirme karşılaştırması olarak IoU .2 kolu denenir; .3 özgün koldur.
   Her olayı ayrı raporlamak, toplam skorun çözülmeyen hatayı gizlemesini önler.
5. Kaynak hash'leri, yeniden oynatılabilir küçük test girdileri, yakın plan
   görüntüler/klipler ve CI regresyonları teslim edilir. Yeni üretim adayının
   kabulü için bütün 11 geliştirme kesitinde eski kişi/forma/kapsam kapıları ve
   ardından önceden ayrılmış kontrol gerekir. Bu tanı koşusu onay sayılmaz.
