# tactic11 — kulüp pilotu: ne yapar, ne yapmaz

Bu belge bir kulübe pilot önerirken masaya konacak tek sayfadır. Her sayı `docs/measurements/`
altındaki bir ölçüm dosyasına dayanır; dosya adı satırın sonunda yazılıdır. Ölçülmemiş hiçbir şey
"yapar" sütununa yazılmaz.

## Önerilen söz

**Maç videosunu akşam yükleyin; sabah tek sayfalık taktik rapor (PDF) hazır olsun.**

Rapor takım düzeyindedir: dilim dilim genişlik, derinlik, kompaktlık, pres ve takım temposu;
maç ortalamasından ayrılan dilimler "öne çıkanlar" olarak listelenir. Yorum ve karar teknik
ekibindir. Örnek: SoccerTrack 117093 ilk yarısından üretilen rapor
(`GET /tracking/matches/{id}/report.pdf`).

## Kanıtlı olanlar

| Ne | Koşul | Sonuç | Kaynak |
|---|---|---|---|
| Uçtan uca yükleme yolu | Sabit geniş açı, gündüz, 30 dk'lık devre | İş tamamlandı, dakikaların %100'ünde kare, kare başına medyan 22 oyuncu, 6 parçanın 0'ı başarısız | `product-full-match-exam-result-attempt4.json` |
| İşlem süresi | Aynı koşu, tek ev bilgisayarı (GPU) | Video süresinin 5,96 katı: 90 dk'lık maç ≈ 9 saat, gece bırakılır | `product-full-match-exam-result-attempt4.json` |
| Oyuncu bulma | Aynı koşu, 20 kare elle sayım | Oyuncuların %95,9'u işaretli, işaretlerin %2,8'i boş (sayan: yapay zekâ, insan değil) | `product-full-match-exam-hand-review-attempt4.json` |
| Takım ayrımı | Sabit kamera, gündüz, 10 dk, referans konumlarla | Eşleşen oyuncuların %91,6'sında takım doğru | `daylight-132877-gsr-telestration.json` |
| Savunma hattı konumu | Aynı ölçüm | Medyan hata 1,89 m; %90'ı 12,1 m içinde | `daylight-132877-gsr-telestration.json` |
| Raporun "öne çıkanlar"ı | Sabit kamera, gündüz, 2 saha × 10 dk, dakikalık dilim, gerçek konuma karşı | Takipteki bulguların 132877'de %72'si, 132831'de %58'i gerçek konumda da var; derinlik bulguları (%27 doğru) rapordan çıkarıldı. Görülmüş veri, kanıtlanmış iyileşme değil | `match-report-vs-gt.json` |
| TV yayınından saha konumu | J.League, gündüz, 2 maç × 6 dk, kör kontrol | Ana kamera karelerinin %81,2'sinde saha konumu bulundu; işaretlere göre medyan hata 0,40 m | `broadcast-track-round4-control-result.json` |

## Yapmadıkları ve bilinmeyenler

- **Gece maçı ölçülmedi.** Türkiye'de maçların çoğu ışık altında oynanır; pilot gündüz maçı ya da
  antrenman kaydıyla sınırlanmalı veya gece ölçümü ayrıca planlanmalı.
- **Oyuncu bazında değil.** İz kimlikleri parçalar arasında taşınmaz
  (`cross_segment_person_identity: false`); "10 numara kaç km koştu" sorusu yanıtlanmaz.
- **Fiziksel yük gerçek konuma karşı doğrulanmadı.** Tempo ve hız payları takım düzeyinde,
  karşılaştırma amaçlıdır; GPS'in yerini tutmaz.
- **Raporun mutlak şekil sayıları kaba.** Genişlik gerçek değerden 3–5 m, derinlik bir sahada medyan 17 m sapıyor; dilimler arası değişim mutlak değerden daha güvenilir (`match-report-vs-gt.json`). "Öne çıkanlar"ın yaklaşık üçte biri yanlış alarm olabilir.
- **Saha yönü bilinmez.** Savunma hattı yüksekliği ve "blok önde/geride" raporda verilmez.
- **TV yayını dar kapsamlı.** Yalnız J.League gündüz yayınında ölçüldü; ana kamera dışı kareler
  ve tekrarlar (J.League'e özgü işaretle) atılır, 90 sn'lik örnekte karelerin %39,5'i konumlandı.
  6 dakikalık kesit yaklaşık 25 dakika sürer. Kulübün kendi geniş açılı kaydı tercih edilmeli.
- **Canlı mod yavaş ve eksik.** Prova: görüntüden yaklaşık 1,5–2 dk geride, segmentlerin %42'si
  işlendi (`live-rehearsal-990602-keep-up.json`). Pilotta canlı söz verilmez.
- **Elle sayım yapay zekâ tarafından yapıldı;** insan gözden geçirmesi yok.

## Pilot önerisi

1. **Süre ve kapsam:** 3–4 maç, kulübün kendi geniş açılı (taktik kamera) kaydı, gündüz.
2. **Teslim:** maç sonrası sabah 08:00'e kadar PDF rapor + arayüzde dilim dilim tablo.
3. **Başarı ölçütü (baştan yazılı):** analistin aynı maç için kendi notlarıyla karşılaştırdığında
   "öne çıkanlar"ın en az yarısını doğru/işe yarar bulması; teslim saatinin tutması.
4. **Kulüpten istenen:** maç videosu (geniş açı), takımların forma renkleri, saha ölçüleri.
5. **Veri ve haklar:** video ve takip verisi kulübün sunucusunda/bilgisayarında işlenir,
   dışarı gönderilmez. Oyuncu kimliği tutulmaz (takım düzeyi), KVKK açısından kişisel veri
   işlenmesi asgaridir; yine de kulübün hukuk birimiyle teyit edilmelidir.

## Sunumdan önce yapılacaklar

- Kulübün bir maç videosuyla uçtan uca koşu ve çıkan PDF'in analistle birlikte okunması.
- Gece maçı için karar: ölçmek ya da pilot dışında bırakmak.
