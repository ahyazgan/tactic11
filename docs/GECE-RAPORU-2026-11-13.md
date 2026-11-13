# Gece raporu — 2026-11-13 (03:00–07:00)

Dal `exam/urun-tam-mac`, PR tactic11#354. Kararlar kullanıcının devriyle Claude tarafından verildi.

## Sonuç

Ürünün yükleme yolu ilk kez uzun bir sabit kamera videosunu baştan sona, çökmeden işledi:
30 dakika, 6/6 parça, 7496 kare. Sınav yine de **kaldı**: 8 otomatik şarttan 7'si geçti,
süre şartı kaldı. Tam maç iddiası hâlâ yok.

## 3. sınav denemesi

Ön kayıt koşudan önce commit edildi (`afe0617`); sonuç
`docs/measurements/product-full-match-exam-result-attempt3.json` dosyasında aynen duruyor.

| Şart | Eşik | Ölçülen | Sonuç |
|---|---|---|---|
| İş biter | `done` | `done`, 6/6 parça | geçti |
| Veritabanına alım | kare sayısı eşit | 7496 = 7496 | geçti |
| İşlem / video süresi | ≤ 5,0 | 5,307 (9552 sn / 1800 sn) | **kaldı** |
| Dakika kapsaması | ≥ 0,95 | 30/30 | geçti |
| Kare başına medyan oyuncu | ≥ 16 | 22 | geçti |
| En az 8 oyunculu kare payı | ≥ 0,80 | 1,00 | geçti |
| Şekil ucu dolu | ≥ 0,90 | 6/6 | geçti |
| Boş disk | ≥ 3 GB | en az 16,57 GB | geçti |

Şart olmayan gözlem: top karelerin %62,7'sinde var.

**Bu koşunun söylemediği şeyler (koşudan önce yazıldı):**
- Tam maç değil, ilk 30 dakika. 1800. saniyeden sonrası dondurulmuş kimlik kontrollerinin
  açılmamış verisi (60–72. segmentler); dokunulmadı.
- Kör değil: 117093'ün ilk 210 saniyesi geliştirmede kullanıldı.
- Konum doğruluğu iddiası yok: kalibrasyon hatası 1,43 m.
- El kontrolü yapılmadı (aşağıda).

**Neden bu video:** istenen 132877 indirilemedi; SoccerTrack v2 Hugging Face token'ı istiyor
ve makinede token yok. Diskteki tek sabit kamera uzun video 117093 ilk yarısıydı.

## Bulunan ve düzeltilen kusurlar

| Kusur | Kanıt | Düzeltme |
|---|---|---|
| İkinci parçadan itibaren işçi çöküyordu | İş 0bd6447d5c logu: `clip offset must resolve to a whole millisecond` | Parça başlangıcı milisaniyeye yuvarlanır (`c3ed6ba`) |
| Dondurulmuş `replay.py` değiştirilmişti, hash sınaması kırmızıydı | `test_guarded_control`, tüm pakette tek hata | Dosya geri alındı; yeniden ısınma `replay_relearn.py`, yalnız ürün işçisi bağlar (`1cb311c`) |
| Bellek yetmeyince iş 50 dakika çalışıp çöküyordu | 2. deneme sonucu | İş başlamadan bellek kapısı (`3d036bb`) |
| Panorama yüklemesinde 6 dilim GPU belleğini taşırıyordu | 7,85 GB ayrılmış + 4,2 GB paylaşılan; 13 dakikada 8 saniyeden az video | Dilim sayısı kare başına 50 dilim sınırıyla düşer (`db6508e`); aynı 30 saniye 172 saniyede bitti |
| `e2e` ve `live_auth` kuruluşta kalıyordu | Playwright 1.60, `ubuntu-latest` 26.04'te tarayıcı kuramıyor | Koşucu `ubuntu-24.04`'e sabitlendi (`cde322c`) |

Ayrıca: el kontrol aracı (`scripts/urun_mac_el_kontrol.py`, `5a9c940`), dört README'nin gerçek
duruma göre yeniden yazılması (`855172c`), kullanımdan kalkan çağrıların temizliği (`31eed5e`).

Doğrulama (son commit, sınav bittikten sonra): pytest 3397 geçti / 106 atlandı / 0 kaldı, ruff
temiz, mypy temiz (631 dosya), CI 11/11 yeşil.

## Açık kalanlar

1. **Süre şartı.** Parçalar 300 saniyelik video için 1541–1641 saniye sürdü (5,1–5,5 kat). Daha
   önce 4K için ölçülen hız 3,3 kattı. Fark ayrıştırılmadı. Koşunun ilk dakikalarında aynı
   makinede test paketi çalıştırıldı; etkisi ölçülmedi ama sonraki parçalar da yavaştı, yani
   tek sebep bu değil.
2. **Bellek kapısı panorama için düşük.** Ayrılabilir bellek koşuda 17,6 → 5,1 GB'a indi; işçi
   bu görüntüde yaklaşık 12,5 GB istiyor, kapı eşiği 11 GB (1080p'de ölçülmüştü).
3. **Ürün süzgeci çalışma anında değiştiriliyor.** `pipeline.py` dondurulmuş olduğu için tekrar
   süzgecinin ürün sürümü işçi başlarken bağlanıyor; ölçülen kod ile ürün kodu bu noktada ayrı.
4. **Tam maç.** Sabit kameralı tam maç videosu ve kontrol kesitlerine dokunmayan bir maç gerekiyor.

## Kullanıcıdan gerekenler

- **El kontrolü (20 kare).** Kareler `data/tracking/out/el_kontrol_attempt3/` altında. Önce
  `NN_ham.jpg`'de sahadaki oyuncuları say, sonra `NN_tahmin.jpg`'de işaretleri kişi ya da hayalet
  diye ayır; `el-kontrol.json` içindeki boş alanları doldur. Şartlar: yakalama ≥ 0,70, hayalet
  payı ≤ 0,20. Bu klasör Claude'un okuma izninin dışında; kareleri Claude denetlemedi.
- **Hugging Face token'ı** (`HF_TOKEN`): 132877 ve diğer sabit kamera maçlarını indirmek için.
- **Karar:** süre şartı 5 kat olarak mı kalsın (o zaman hız işi öncelik), yoksa maç sonrası
  kullanım için gevşetilsin mi. Eşiği sonuç görüldükten sonra değiştirmek bu denemeyi geçirmez;
  yalnız bir sonraki deneme için geçerli olur.
