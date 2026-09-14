# BACKLOG.md — Work Queue

> Claude Code pulls the next unchecked item from here automatically (see CLAUDE.md §7).
> Format per item: `- [ ] <goal>` then a `Done when:` line.
> Check off completed items with the commit SHA: `- [x] <goal>  (abc1234)`
> Append new sub-tasks here instead of stopping to ask.

-----

## Now (current session — work top to bottom, don't pause between items)

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
