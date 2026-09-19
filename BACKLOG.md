# BACKLOG.md — Work Queue

> Claude Code pulls the next unchecked item from here automatically (see CLAUDE.md §7).
> Format per item: `- [ ] <goal>` then a `Done when:` line.
> Check off completed items with the commit SHA: `- [x] <goal>  (abc1234)`
> Append new sub-tasks here instead of stopping to ask.

-----

## Now (current session — work top to bottom, don't pause between items)

- [x] Codex kamera: sistemi gerçek dedektör/aktarım ile doğrula; bağımsız motor ve renk uzlaşısını geliştirmede ölçerek açık seçimle entegre et. (d25c7a0)
  Done when: 30 saniyelik gerçek RF-DETR/OSNet/top ROI çıktısı ve bellek DB aktarımı doğrulandı; 11 kesitte üretim/araştırma eşitliği, 22 eski çıktı ve 164.772 gözlem birebir korundu. Son kodda 83 CV + 4 kanıt zinciri testi, Ruff ve mypy geçti; tam uygulama koşusu 2.926 başarılı/51 atlanan test verdi. Gündüz etiketlerinde yalnız bir yanlış kişi birleşmesi düzeldi; forma doğruluğu korunur. Sonuç: docs/KIMLIK-UZLASISI-SONUCLARI.md. Deneysel consensus varsayılan değil; yeni kontrol ve gerçek zaman hedefi henüz geçilmedi.

- [x] Codex kamera: sabitlenmiş uzlaşı adayını önceden ayrılmış iki gündüz ve iki gece kontrolünde kör etiketlerle değerlendir. (27e7800; sonuç raporu bu değişiklikte)
  Done when: kod/model/parametre/plan hashleri kontrol açılmadan sabit; bütün başlangıç kutuları ve kişi ilişkileri tahminden bağımsız etiketli, tüm yeni ayrımlar incelenmiş, kaynak bazında gerileme kapıları ve kapsam sınırları raporlu. Plan: docs/KIMLIK-UZLASISI-KONTROL-PLANI.md. Gerileme veya bağımsız olumlu ayrım yoksa varsayılan değişmez.

- [x] Codex kamera: Torch ana dedektöründe gerçek dilim sayısıyla gruplamayı düzelt, eski/yeni çıktı eşitliğini yeni gündüz ve gece kesitlerinde doğrula. (154968d; kontrol 4f1ec8a/e0e06a5)
  Done when: geliştirmede gündüz %28,4/gece %5,8 süre azalması, iki kontrolün dörder tekrarında kare ve olay eşitliği, 2.947 uygulama + 32 ilgili CV testi ve kanıt zinciri raporlu. İlk gece aralık hatası korunup görüntü açılmadan ikame edildi; aday kodu değişmedi. Sonuç: docs/TORCH-GRUPLAMA-SONUCLARI.md. Gerçek zaman veya kimlik doğruluğu tamamlanmış sayılmaz.

- [x] Codex kamera: ayrı top ROI modelini yoğun gözlem ve yeni gündüz/gece kontrolleriyle sınayıp varsayılan kararını ver. (6567f89; kontrol 7fa50fa)
  Done when: gerçek iki kol/iki tekrar, bütünlük ve ayrıntılı top/oyuncu eşitliği raporlu. Gündüz iki son kare farklı olduğu için varsayılan kapalı; gece çıktı eşit fakat hız artmadı. Sonuç: docs/ROI-GRUPLAMA-SONUCLARI.md. Açık deneysel seçim video/canlı yollarında korunur.

- [x] Codex kamera: genel/spor OSNet, GTA kısa parça bağlantısı, optik akış ve mevcut palet desteğini tüm eski ayrımlarda ölç.
  Done when: yedi ayrımın tamamı, sabit model/kod kaynakları, negatif bulgular, hareket görselleri ve 15 kesit önbellek tanısı raporlu. RGB palet adayı altı doğru ayrımı koruyup beyaz 6 yanlış bölünmesini reddediyor; bağımsız kontrol başarısı değildir. Sonuç: docs/KIMLIK-GORUNUS-TANISI.md; toplu durum: docs/TAKIP-ENTEGRASYON-DURUMU.md.

- [ ] Codex kamera: kontrolde görülen beyaz 6 numara yanlış bölünmesini geliştirme senaryosuna bağla; görünüş/renk/hareket desteğini tüm ayrımlarda karşılaştır.
  Done when: yanlış ayrımın kaynak/karar izi açıklanır, alternatif yalnız geliştirmede seçilir; hız ve kutu/kimlik/takım kapsamı ölçülür, sonraki aday yeni kontrolden geçmeden varsayılan olmaz. Önceki aday dört kontrolde üç doğru/bir yanlış ayrım üretti ve reddedildi. Sonuç: docs/KIMLIK-UZLASISI-KONTROL-SONUCLARI.md.

- [x] Codex kamera: kaybolan iki gündüz kimlik bağlantısını görüntü/karar iziyle ayır ve tekrarlanabilir regresyon senaryolarına bağla. (f31e088)
  Done when: 407 kaynak örnek karesinden iki hata yeniden üretildi; görüntü/karar izi ve dört tanı kolu kaydedildi. 17 yeni test, eski korumalarla birlikte 63 test geçti. Sonuç: docs/KIMLIK-HATA-DENETIMI-SONUCLARI.md. Beyazda parçalı kutu + hareket kapısı, mavide oyuncu/hakem alt-gövde karışımı ayrıldı. Oracle müdahaleleri üretim düzeltmesi değildir; üretim kodu değişmedi, yeni kontrol açılmadı.

- [x] Codex kamera: Deep OC-SORT + OSNet görünüş eşleştirmesini ölç ve video/canlı takip motoru seçimine entegre et. (b2310a9)
  Done when: sabit resmî model/kod, 11 kesitte üç kol, video/sıcak/izole canlı seçim, 22 birebir eski çıktı ve 164.772 kişi gözlemi; 95 ilgili CV testi ve 2.893 uygulama testi geçti. Sonuç: docs/TAKIP-REID-SONUCLARI.md. ReID bazı kişi çiftlerini iyileştirdi, fakat iki eski doğru gündüz bağlantısını kaybetti ve bazı forma hatalarını artırdı; deneysel açık seçimle entegre, varsayılan ByteTrack korundu, yeni kontrol açılmadı.

- [x] Codex kamera: açık kaynak ByteTrack/BoT-SORT/OC-SORT motorlarını aynı tespitlerde karşılaştır; Deep OC-SORT uyumluluğunu incele. (3eb023b)
  Done when: 11 kesit, motor başına 4.125 kare, 44 birebir tekrar; kişi/forma/kapsam ve süre ölçümleri, 65 ilgili CV testi, 2.882 uygulama testi ve PR kontrolleri tamamlandı. Sonuç: docs/TAKIP-MOTORU-KARSILASTIRMA-SONUCLARI.md. Hiçbir alternatif tüm geliştirme kapılarını geçmedi; üretim motoru korundu, yeni kontrol açılmadı. Deep OC-SORT'un kaynak/CUDA uyumu incelendi; ReID çıkarımı henüz ölçülmedi.

- [x] Codex kamera: kişi kimliği/forma zincirini ortak üretim akışında düzelt; mükerrer parçaları, kimlik devrini, güvenli bağlantıyı ve canlı segment kimliklerini birlikte doğrula. (401adb3, 9f571a3, 8a66672)
  Done when: değişmez kutularla üretim tekrarı, kişi bağlantısı denetimi, dondurulmuş kontrol, video/canlı/önizleme ve bütün PR kontrolleri tamamlandı. 2.877 uygulama, 164 ilgili CV ve gerçek PostgreSQL'de 14 test geçti. Sonuç: docs/SABIT-KAMERA-KIMLIK-SONUCLARI.md. Gündüz kontrolünde aynı kişi bağlantısı 92/134→90/134 gerilediği için deneysel profil otomatik açılmadı; gündüz kontrolünün bağımsızlık sınırları raporlu, genel kişi kimliği doğruluğu tamamlanmış sayılmaz.

- [x] Codex kamera: kesme/tekrar/kalibrasyon boşluğunda kimlik ve forma geçmişini ayır, çekimler arası hız hesabını kes; takip süresini aynı tespitlerde ölç. (76797ec)
  Done when: 13 gerçek CV/çekirdek testi, 87 ilgili uygulama testi, 2.635 tam yerel test; üretim yolunda 1.125 sabit kamera karesinin oyuncu/renk geçmişi eşit. Sonuç: docs/TAKIP-SUREKLILIGI-SONUCLARI.md. Daha uzun bekleme gündüz doğruyu 195→194 düşürüp karışık ID'yi 7→8 artırdığı için reddedildi; gerçek süre raporlanıyor. Sabit kamerada oyuncular arası ID değişimi ve genel forma/olay doğruluğu tamamlanmış sayılmaz.

- [x] Codex kamera: saha çevresindeki sahte takipleri ayır, kamera bazında doğrula ve önizleme zaman/boyut/geometri hatalarını düzelt. (a9079c1)
  Done when: dondurulmuş filtre, 248 yeni kör kontrol kutusu, iki yeni gece klibi, gerçek dedektör tekrarında 375 karenin birebir eşleşmesi ve okunabilir önizleme. Sonuç: docs/OYUNCU-SUZGECI-SONUCLARI.md. Gündüz 25 sahte kutu→0, forma kaybı 0, doğru 83→95; gece ek başka-renk ataması nedeniyle yalnız 117093 profili etkin. 89 ilgili test geçti; genel doğruluk/oyuncu kimliği/olay doğruluğu tamamlanmış sayılmaz.

- [x] Codex kamera: aydınlık 117093 maçını ayrı kalibrasyonla işle, kör dış kontrolü ölç ve başarısız ışık varsayılanını geri al. (417b25e)
  Done when: üç kaynak klip/hash, 172 kutu etiketi, 65 saha işareti, aynı kutularda ham/çim karşılaştırması, üretim yolu eşitliği ve takip önizlemesi hazır. Sonuç: docs/GUNDUZ-MACI-SONUCLARI.md; kontrol ham 53/13/8, çim 16/54/4 (doğru/yanlış/atanamayan). Ham varsayılan, normalizasyon açık seçimle korunur. 29 ilgili ve 2.594 tam yerel test geçti, 1 atlandı. Kişi olmayan tespit ve olay doğruluğu çözülmüş sayılmaz.

- [x] Codex kamera: gölge düzeltmesini yeni kontrol klipleriyle yeniden dene ve geçen yerel çim normalizasyonunu takip hattına bağla. (93d2413)
  Done when: iki ayrı dondurulmuş deney, yeni 149 kör kutu etiketi, üretim fonksiyonuyla 54.103 gözlemin aynı sonucu vermesi, video/canlı entegrasyonu ve regresyonlar. Sonuç: docs/YEREL-CIM-ISIGI-SONUCLARI.md; yeni kontrol 54→56 doğru, 7→4 yanlış, 5→6 atanamayan. 80 ilgili ve 2.569 tam yerel test geçti; 1 atlandı. Genel maçlar arası doğruluk hedefi tamamlanmış sayılmaz.

- [x] Codex kamera: gölgeli forma için doğrudan görüntü etiketleriyle medyan/parlak dörtte birlik deneyini dondurulmuş kontrolde ölç. (943d411)
  Done when: tahminden bağımsız 142 kutu, kör görüntü incelemesi, geliştirme/kontrol ayrımı ve kabul regresyonları. Sonuç: docs/GOLGE-FORMA-SONUCLARI.md; 58 ilgili test geçti. Geliştirme 36→41 doğru, kontrol 66→65 doğru; aday üretime alınmadı. Otomatik PR tamamlama yetkisi AGENTS.md'de kayıtlı (f7baf5b).

- [x] Codex kamera: konumsal takım uyuşmazlıklarını görüntü kanıtıyla ayır ve tekrar üretilebilir hata tanısı ekle. (407a565)
  Done when: geliştirme/kontrol tanısı, kaynak kutu görüntüleri ve görsel inceleme notları, anlamlı regresyonlar ve lint/tip kontrolü. Sonuç: docs/TAKIM-HATA-TANISI-SONUCLARI.md; 49 ilgili test geçti. %81,11 ve 119 uyuşmazlık gerçek forma doğruluğu/hata sayısı olarak kullanılamaz; model değişmedi.

- [x] Codex kamera: ayırt edilemeyen forma renklerinden takım üretmeyi ve geçersiz canlı renk çapasını önle. (b52767e)
  Done when: tek renk/canlı geçiş regresyonları, aynı geliştirme-kontrol kayıtlarında ölçüm ve tam test/lint/tip kontrolü. Sonuç: docs/TAKIM-RENK-BELIRSIZLIGI-SONUCLARI.md; 2529 test geçti. Kontrol doğruluğu %81,11 kaldı; genel doğruluk hedefi henüz geçilmedi.

- [x] Karne incelemesi: yetersiz bayrakla başarı hükmünü ve aynı dakikadaki oyuncu sayımını düzelt; özgün veride yeniden ölç. (8c7b938)
  Done when: regresyonlar ve birleşik testler temiz, 100 maçlık özgün girdi SHA-256 ile eşleşir, yeni ölçüm ve sınırlar raporlanır. Sonuç: docs/KARNE-DUZELTME-SONUCLARI.md.

- [x] Top adaylarını, oyuncu çevresi ROI aramasını ve saha çizgisi kalibrasyonunu dondurulmuş kontrolle karşılaştır; farklı piksel boyutunda kalibrasyonu reddet. (4b8d149)
  Done when: aynı tam kare tespitleriyle tekrar takip, çizgi/pas/takım ölçümleri ve başarısız deney raporu; test/lint/tip kontrolleri temiz. Sonuç: docs/TOP-SECIMI-SONUCLARI.md. Alternatifler doğruluk kapısını geçmedi; varsayılanlar değiştirilmedi.

- [x] Video top/pas/top kazanımı kanıt zincirini düzelt; yoğun kare denemesini ve gerçek olay eşleşmesini ölç. (b1eb581)
  Done when: kamera/zaman/top belirsizliği korunur; video/canlı JSON→DB→domain zinciri ve kısmi savunma koruması testli; birebir GT karşılaştırması ve başarısız deneyler raporlu. Sonuç: docs/VIDEO-OLAY-SONUCLARI.md. Pas duyarlılığı ve gerçek görüntüde savunma doğruluğu hedefleri geçilmedi; yoğun olay akışı varsayılan kapalı.

- [x] Sabit kamera: takım renklerine sızan kısa takipleri/farklı renkleri ele ve GT ile ölç. (8ae76c3)
  Done when: aynı gözlemlerle geliştirme/kontrol karşılaştırması, oyuncu kaybı ve pas/savunma başlangıç raporu; test/lint/tip kontrolleri temiz. Kapsam: docs/SABIT-KAMERA-SINYAL-PLANI.md.

- [x] Mobile sidebar drawer  (ba07618)
  Done when: drawer opens/closes on mobile breakpoints, nav items reachable, tsc+build clean, committed.
- [x] Decisions API load-perf cache  (b2c55d6)
  Done when: /decisions endpoints cached with sane TTL, repeat-load latency measurably lower, tests cover cache hit/miss, committed.
- [x] End-to-end smoke run — La Liga match  (bc44854)
  Done when: full decision flow (live → apply → track → reconcile) runs green on a La Liga fixture in demo mode, no console errors, committed.

-----

## Next (pull these once "Now" is clear)

- [x] return_to_play engine  (ceec769)
  Done when: engine implemented in engine layer, wired api→ai→engine→domain, unit tests green, committed.
- [x] minutes_management engine  (8a9f839)
  Done when: as above.
- [x] congestion_risk engine  (a94952d)
  Done when: as above.
- [x] weekly_digest output motor  (3951a49)
  Done when: generates digest from real engine outputs, rendered in UI, tested, committed.
- [x] prematch_brief output motor  (b2083cf)
  Done when: as above.

-----

## Later (lower priority — only if Now + Next clear)

- [ ] PDF report export for scout_report_generator
- [ ] Push/email delivery for digests (currently pull-only)
- [ ] i18n scaffold for English UI
- [x] Security headers (CSP / HSTS / X-Frame-Options / X-Content-Type-Options)  (b067175)
- [x] Retry + circuit-breaker on external API calls  (868f289)
- [x] Liveness/readiness split on /health  (pre-existing — /healthz + /readyz)

-----

## Done (archive — keep last ~10 for context)

- [x] LiveDecisionDigestAgent → AI brief paneli  (5b36b56, PR #193)
- [x] Video clip stub + PWA offline shell + pilot pitch  (97d6eba, PR #192)
- [x] Audit fixes — replay commit + docs eksikleri  (dd08676, PR #191)
- [x] 3 yeni engine (hot_hand/set_piece/referee) + La Liga smoke  (d2da3d1, PR #190)
- [x] Decisions UI cilası — hub tiles + tooltipler + Karar Yansıt  (9f6646b, PR #189)
- [x] Closing/foul/star engines + frontend + ingest derinliği  (cad18bc, PR #188)

-----

## Notes / blockers (anything needing human eyes)

- (none currently)
