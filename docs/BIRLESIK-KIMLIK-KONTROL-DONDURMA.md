# Birleşik kimlik kontrolü: dondurma kaydı

10 Ekim 2026. `guarded` üretim entegrasyonu PR #283 / `8f4e66a` ile
birleşti; son PR ve ana dal CI/Vercel kontrolleri geçti. Aynı aday şimdi
yeni zaman aralıklarında kontrol için sabitlendi. Bu belge kontrol sonucu
veya varsayılan takip motorunu değiştirme kararı değildir.

Karar: [identity-guarded-frozen-decision.json](measurements/identity-guarded-frozen-decision.json).
SHA-256: `bdcc0d433f1625ae4c3a19521a944f5ac5919baee3a15353dd90c6bec3b27cc8`.
`code_commit`, üretim adayının taban commitini belirtir; yeni kontrol
araçlarının kesin içeriği de karardaki kod hashlerine dahildir. Karar ve
araçlar Git'e kaydedilmeden yeni görüntüye erişen komutlar çalışmaz.

- 103 kod dosyası: üretim takip yolu, eski karşılaştırma adayları, edinim/
  puanlama araçları ve kontrol testleri.
- 19 girdi/kanıt dosyası: modeller, sabit geliştirme çapaları/kalibrasyon
  şablonları, plan/protokol, tam kaynak videolar ve tamamlanmış entegrasyon
  kanıtları. İki tam video eski donmuş kaynak hashleriyle eşleşti.
- Python 3.12.10 ve dokuz paket sürümü sabit; tek video çözücü iş parçacığı
  ve kapalı gradyan hesabı çalışma biçimine dahil.
- Gündüz 117093: 2040–2070 ve 2160–2190 sn. Gece 117092: 2220–2250 ve
  2280–2310 sn. Aynı maçların yeni zamanlarıdır; bağımsız maç değildir.

Üretim kodu ve eski donmuş kontrol dosyaları değiştirilmedi. Yeni araçlar
eski kaynak kutusu puanlayıcılarını kullanır. Her iki grup için bütün
kaynak başlangıç/bitiş kutuları etiketlenip etiketler ve mühürleri Git'e
kaydedilmeden tahmin tekrarı açılmaz. Tek bir eski doğru ilişkinin kaybı,
toplam sayılar değişmese de gerileme sayılır. Bütün hareket önerileri,
ayrımlar, geri dönüşler ve ek kutular ayrıca kaynakta incelenmelidir.

Doğrulama: **67 test geçti**; eksik edinim, değiştirilmiş kaynak/kod/sürüm,
eksik veya çelişkili etiket, kayıp kutu, değişen takım/güven ve önceki doğru
ilişki kaybı denetlendi. Üç kol, gerçek ByteTrack ve Deep OC-SORT takipçileri
ile sentetik kaynakta çalıştırıldı; yalnız gömme ağı yerine sabit test
öznitelikleri kullanıldı. Bu test yeni görüntülerde OSNet doğruluğu değildir.
Ruff ve iki yeni araç için mypy geçti. Yeni kontrol görüntüleri bu kayıt
oluşturulurken açılmadı; ham edinim, kör etiket, tahmin ve değerlendirme açık.

[Plan ve komut sırası](BIRLESIK-KIMLIK-KONTROL-PLANI.md),
[önceki gerçek video/canlı doğrulaması](BIRLESIK-KIMLIK-VIDEO-ENTEGRASYONU.md).
