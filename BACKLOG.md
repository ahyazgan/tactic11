# BACKLOG.md â€” Work Queue

> Current camera work continues through Codex in `football-intelligence` / `codex-work` (see AGENTS.md).
> Preserve the adjacent Claude worktree; unrelated backlog items do not expand the current camera task.
> Format per item: `- [ ] <goal>` then a `Done when:` line.
> Check off completed items with the commit SHA: `- [x] <goal>  (abc1234)`
> Append new sub-tasks here instead of stopping to ask.

-----

## Now (current session â€” work top to bottom, don't pause between items)

### Claude otonom oturum 2026-11-01 (12:00'ye kadar) â€” gÃ¼nlÃ¼k: docs/CALISMA-GUNLUGU-2026-11-01.md

- [x] DedektÃ¶r v2: eÄŸitim kliplerindeki toplarÄ± eski modelle (Ã¶ÄŸretmen) etiketle, 128058'i tamamen teste ayÄ±r, yeniden eÄŸit ve Ã¶n kayÄ±tlÄ± ÅŸartlarla Ã¶lÃ§.
  Done when: Ã¶n kayÄ±t eÄŸitimden Ã¶nce commit; 128058 oyuncu testi, TeamTrack top testi, 117092 panorama (tekrar) Ã¶lÃ§Ã¼ldÃ¼; sonuÃ§ belgede, Ã¼retim yalnÄ±z ÅŸartlar geÃ§erse deÄŸiÅŸir. (3a9f38e: 6/7 ÅŸart, terfi yok; kullanÄ±cÄ± kararÄ± bekliyor)
- [x] Telestrasyonu canlÄ± moda baÄŸla: her iÅŸlenen segment iÃ§in Ã§izim Ã¶ÄŸeleri (marks) ve telestrasyonlu video Ã¼ret; panelde video Ã¼stÃ¼ katman.
  Done when: canli_mac akÄ±ÅŸÄ±nda segment baÅŸÄ±na marks JSON + mp4; dondurulmuÅŸ dosyalara dokunulmadÄ±; testler yeÅŸil. (PR #301, #302)
- [x] CanlÄ± prova: 1080p Ã¶n ayarÄ±yla gerÃ§ek hÄ±zda 10+ dk prova, gecikme ve doÄŸruluk Ã¶lÃ§Ã¼mÃ¼.
  Done when: gecikme eÄŸrisi ve segment sÃ¼releri belgede; Ã¶n ayar Ã¶nerisi Ã¶lÃ§Ã¼me dayalÄ±. (docs/CANLI-HIZ-VE-PROVA.md; 6 dk prova, kaynak 6 dk)
- [x] HÄ±z: ONNX arka ucu ve 1080p ile segment sÃ¼resini Ã¶lÃ§; gerÃ§ek zamana ne kadar yaklaÅŸÄ±ldÄ±ÄŸÄ±nÄ± raporla.
  Done when: aynÄ± segmentlerde torch/onnx Ã— 4K/1080p sÃ¼re ve tespit oranÄ± tablosu. (1080p Ã— 4/3/2 dilim; 4K sÃ¼re Ã¶nceki Ã¶lÃ§Ã¼mde ~100 sn; gerÃ§ek zamana ulaÅŸÄ±lmadÄ± â†’ --keep-up)


- [x] Codex devamÄ±: GitHub ana dalÄ±nÄ± al, baÅŸka projelerin portlarÄ±nÄ± koruyarak gerÃ§ek API arayÃ¼zÃ¼nÃ¼ aÃ§; video giriÅŸini ve eksik edinim kapÄ±sÄ±nÄ± doÄŸrula.
  Done when: 3100/8100 baÅŸlatÄ±cÄ±sÄ±, gerÃ§ek-mod giriÅŸ/401 gÃ¶rÃ¼nÃ¼rlÃ¼ÄŸÃ¼, 5 giriÅŸ tarayÄ±cÄ± testi, gerÃ§ek hesaptan 12 baÅŸarÄ±lÄ± takip isteÄŸi ve 17 ham edinim testi. SonuÃ§: docs/CODEX-DEVAM-DURUMU-2026-10-09.md. Sonraki Ã¶lÃ§Ã¼mlÃ¼ koÅŸuda gece ham edinimi tamamlandÄ±; palet adayÄ± varsayÄ±lan yapÄ±lmadÄ±.

- [x] Codex kamera: dondurulmuÅŸ palet adayÄ±nÄ±n dÃ¶rt kesitteki kÃ¶r kaynak etiketlerini tamamla, mÃ¼hÃ¼rle ve Ã¼Ã§ kolu bÃ¼tÃ¼n ayrÄ±mlarÄ±yla karÅŸÄ±laÅŸtÄ±r. (etiket mÃ¼hrÃ¼ e3d9618; sonuÃ§ raporu bu deÄŸiÅŸiklikte)
  Done when: 273 baÅŸlangÄ±Ã§, 282 bitiÅŸ kutusu ve 322 iliÅŸki kaynak gÃ¶rÃ¼ntÃ¼den incelendi; tahmin aÃ§Ä±lmadan hash ile mÃ¼hÃ¼rlendi. DÃ¶rt kesitte 1.500 ham Ã¶rnek ve 12 tekrar geÃ§ti; Ã¼Ã§ kolun 31.771 Ã§Ä±ktÄ± kiÅŸi gÃ¶zlemi birebir aynÄ±. Sonraki incelemede iki ters bitiÅŸ indeksi bulundu; mÃ¼hÃ¼rlÃ¼ kayÄ±t korunup aÃ§Ä±kÃ§a tahmin sonrasÄ± dÃ¼zeltme eklendi. Yeni/reddedilen sÄ±nÄ±r yok; olumlu kontrol dÃ¼zeltmesi yok, Ã¼retime terfi yok. Tek AI ve aynÄ± maÃ§tan kontrol sÄ±nÄ±rlarÄ± raporlu. SonuÃ§: docs/PALET-UZLASISI-KONTROL-SONUCLARI.md.

- [x] Codex kamera: kÄ±sa kopma iÃ§in hareket, tekil eÅŸleÅŸme, rakip yakÄ±nlÄ±ÄŸÄ± ve palet/destek ayrÄ±mÄ±nÄ± 11 eski + 4 tÃ¼ketilmiÅŸ palet kesitinde Ã¶lÃ§.
  Done when: iki aynÄ±-kiÅŸi iliÅŸkisi ve bir yanlÄ±ÅŸ birleÅŸme dÃ¼zeldi; 114.602 eski gÃ¶zlem ve forma kararlarÄ± korundu. 16 Ã¶neriden 14'Ã¼ seÃ§ildi, 3 kimlik ayrÄ±mÄ±; bir kayÄ±p kutu tÃ¼m-kesit geri dÃ¶nÃ¼ÅŸÃ¼yle korundu. 42 yeni test, kaynak/koÅŸu hashleri, baÅŸarÄ±sÄ±z bellek koÅŸusu ve 26 Ã¶nerinin tek-AI gÃ¶rÃ¼ntÃ¼ incelemesi raporlu. SonuÃ§: docs/KISA-KOPMA-GELISTIRME-SONUCLARI.md. CanlÄ± entegrasyon/varsayÄ±lan terfisi veya yeni kontrol baÅŸarÄ±sÄ± deÄŸildir.

- [x] Codex kamera: kÄ±sa kopma adayÄ±nÄ± Ã¶nceki dÃ¶rt uzlaÅŸÄ± kesitiyle toplam 19 bilinen kesitte geniÅŸlet; altÄ± doÄŸru ayrÄ±mÄ± ve beyaz 6 korumasÄ±nÄ± doÄŸrula, sonra canlÄ± entegrasyonunu sabitle. (entegrasyon ef2a4c3; kontrol dondurmasÄ± bu deÄŸiÅŸiklikte)
  Done when: gÃ¼ndÃ¼z 60/62 ve gece 80/82 dahil kaynak bazÄ±nda eski doÄŸru iliÅŸkiler/kapsam korunmuÅŸ, eski doÄŸru ayrÄ±mlar kaybolmamÄ±ÅŸ; iki akÄ±ÅŸÄ±n kimlik/forma kanÄ±tÄ± ve gecikmeli ayrÄ±m video/canlÄ± yollarda eÅŸit. Yeni kontrol aÃ§Ä±lmadan kod/model/parametre ve kabul koÅŸullarÄ± dondurulur.
  Ä°lerleme: 19 kesit / 7.125 Ã¶rnek tamamlandÄ±; 144.623 eski gÃ¶zlem ve forma kararÄ± korundu. BirleÅŸik aday altÄ± doÄŸru ayrÄ±mÄ± ve beyaz 6 korumasÄ±nÄ± geÃ§ti; eski yÃ¶ntemin 15 kesit / 112.852 gÃ¶zlemi birebir Ã¼retildi. Ãœretim `guarded` yolu 19/19 araÅŸtÄ±rma Ã§Ä±ktÄ±sÄ±nÄ± gerÃ§ek RGB/OSNet ile aynen verdi; 2.375 kare / 48.227 oyuncu kaydÄ± bellek DB aktarÄ±mÄ±nda korundu. 22 eski varsayÄ±lan Ã§Ä±ktÄ± / 164.772 gÃ¶zlem deÄŸiÅŸmedi. GerÃ§ek RF-DETR/top ROI ile gÃ¼ndÃ¼z ve gece kayÄ±tlÄ±/canlÄ± kare, kimlik, olay ve Ã¶nizleme eÅŸitliÄŸi geÃ§ti; 500 kare / 10.618 oyuncu / 16 olay kaydÄ± bellek DB kontrolÃ¼nden geÃ§ti. 150 ilgili CV ve 3.104 uygulama testi geÃ§ti. Entegrasyon tamam; yeni kontrol iÃ§in araÃ§/kod/model dondurmasÄ±, etiket ve deÄŸerlendirme aÃ§Ä±k. 30 saniyelik gerÃ§ek koÅŸular 231â€“359 sn sÃ¼rdÃ¼; gerÃ§ek zaman hedefi saÄŸlanmadÄ±. KanÄ±t: docs/BIRLESIK-KIMLIK-VIDEO-ENTEGRASYONU.md; gÃ¶rÃ¼ntÃ¼ aÃ§Ä±lmadan hazÄ±rlanan sonraki plan: docs/BIRLESIK-KIMLIK-KONTROL-PLANI.md.
  Dondurma: 103 kod ve 19 girdi/kanÄ±t hash'i, ortam sÃ¼rÃ¼mleri ve dÃ¶rt yeni aralÄ±k sabitlendi; 67 ilgili test geÃ§ti. Yeni gÃ¶rÃ¼ntÃ¼ler aÃ§Ä±lmadan karar kaydedildi. KanÄ±t: docs/BIRLESIK-KIMLIK-KONTROL-DONDURMA.md. Ã–nceki paragraftaki aÃ§Ä±k dondurma adÄ±mÄ± bu kayÄ±tla tamamlandÄ±; baÄŸÄ±msÄ±z olumlu kontrol sonucu henÃ¼z yok.

- [ ] Codex kamera: dondurulmuÅŸ birleÅŸik adayÄ± gÃ¼ndÃ¼z 68/72 ve gece 74/76 kesitlerinde kÃ¶r kaynak etiketleriyle deÄŸerlendir.
  Done when: dÃ¶rt kesitte 375'er tam ham Ã¶rnek ve kaynak/kod/model bÃ¼tÃ¼nlÃ¼ÄŸÃ¼ doÄŸrulanmÄ±ÅŸ; bÃ¼tÃ¼n baÅŸlangÄ±Ã§/bitiÅŸ kutularÄ± ve kiÅŸi iliÅŸkileri tahminlerden Ã¶nce etiketlenip mÃ¼hÃ¼rlenmiÅŸ; Ã¼Ã§ kol aynÄ± girdilerde puanlanmÄ±ÅŸ; her kaynaÄŸÄ±n gerilemeleri ile bÃ¼tÃ¼n Ã¶neri/ayrÄ±m/geri dÃ¶nÃ¼ÅŸleri gÃ¶rÃ¼ntÃ¼de deÄŸerlendirilmiÅŸ. Olumsuz veya belirsiz sonuÃ§ aÃ§Ä±kÃ§a raporlanÄ±r; doÄŸrulanmÄ±ÅŸ olumlu dÃ¼zeltme olmadan genel doÄŸruluk/varsayÄ±lan terfisi ilan edilmez. Plan: docs/BIRLESIK-KIMLIK-KONTROL-PLANI.md. GerÃ§ek kiÅŸi/kadro, top/olay ve gerÃ§ek zaman hedefleri ayrÄ±ca aÃ§Ä±k kalÄ±r.

- [ ] Codex kamera: tÃ¼ketilen palet kontrolÃ¼ndeki tam/kÄ±smi kutu kopmalarÄ±nÄ±, Ã¶rtÃ¼ÅŸmede kimlik devrini ve gece forma hatalarÄ±nÄ± geliÅŸtirme senaryolarÄ±nda ayÄ±r.
  Done when: etiket dÃ¼zeltmesinden sonraki tanÄ± sayÄ±mlarÄ±yla 11 yanlÄ±ÅŸ aynÄ±-kiÅŸi iliÅŸkisi, 1 yanlÄ±ÅŸ farklÄ±-kiÅŸi birleÅŸmesi, 63 kapsam dÄ±ÅŸÄ± iliÅŸki ve gece forma/sahte kutu hatalarÄ± kaynak/karar izine baÄŸlÄ±; dÃ¼zeltme yalnÄ±z geliÅŸtirmede seÃ§ilmiÅŸ, eski doÄŸru ayrÄ±mlar ve kutu/forma kapsamÄ± korunmuÅŸ. Yeni aday baÅŸka kontrol aÃ§Ä±lmadan dondurulur; bu dÃ¶rt kesit yeniden baÄŸÄ±msÄ±z baÅŸarÄ± sayÄ±lmaz.

- [x] Codex kamera: sistemi gerÃ§ek dedektÃ¶r/aktarÄ±m ile doÄŸrula; baÄŸÄ±msÄ±z motor ve renk uzlaÅŸÄ±sÄ±nÄ± geliÅŸtirmede Ã¶lÃ§erek aÃ§Ä±k seÃ§imle entegre et. (d25c7a0)
  Done when: 30 saniyelik gerÃ§ek RF-DETR/OSNet/top ROI Ã§Ä±ktÄ±sÄ± ve bellek DB aktarÄ±mÄ± doÄŸrulandÄ±; 11 kesitte Ã¼retim/araÅŸtÄ±rma eÅŸitliÄŸi, 22 eski Ã§Ä±ktÄ± ve 164.772 gÃ¶zlem birebir korundu. Son kodda 83 CV + 4 kanÄ±t zinciri testi, Ruff ve mypy geÃ§ti; tam uygulama koÅŸusu 2.926 baÅŸarÄ±lÄ±/51 atlanan test verdi. GÃ¼ndÃ¼z etiketlerinde yalnÄ±z bir yanlÄ±ÅŸ kiÅŸi birleÅŸmesi dÃ¼zeldi; forma doÄŸruluÄŸu korunur. SonuÃ§: docs/KIMLIK-UZLASISI-SONUCLARI.md. Deneysel consensus varsayÄ±lan deÄŸil; yeni kontrol ve gerÃ§ek zaman hedefi henÃ¼z geÃ§ilmedi.

- [x] Codex kamera: sabitlenmiÅŸ uzlaÅŸÄ± adayÄ±nÄ± Ã¶nceden ayrÄ±lmÄ±ÅŸ iki gÃ¼ndÃ¼z ve iki gece kontrolÃ¼nde kÃ¶r etiketlerle deÄŸerlendir. (27e7800; sonuÃ§ raporu bu deÄŸiÅŸiklikte)
  Done when: kod/model/parametre/plan hashleri kontrol aÃ§Ä±lmadan sabit; bÃ¼tÃ¼n baÅŸlangÄ±Ã§ kutularÄ± ve kiÅŸi iliÅŸkileri tahminden baÄŸÄ±msÄ±z etiketli, tÃ¼m yeni ayrÄ±mlar incelenmiÅŸ, kaynak bazÄ±nda gerileme kapÄ±larÄ± ve kapsam sÄ±nÄ±rlarÄ± raporlu. Plan: docs/KIMLIK-UZLASISI-KONTROL-PLANI.md. Gerileme veya baÄŸÄ±msÄ±z olumlu ayrÄ±m yoksa varsayÄ±lan deÄŸiÅŸmez.

- [x] Codex kamera: Torch ana dedektÃ¶rÃ¼nde gerÃ§ek dilim sayÄ±sÄ±yla gruplamayÄ± dÃ¼zelt, eski/yeni Ã§Ä±ktÄ± eÅŸitliÄŸini yeni gÃ¼ndÃ¼z ve gece kesitlerinde doÄŸrula. (154968d; kontrol 4f1ec8a/e0e06a5)
  Done when: geliÅŸtirmede gÃ¼ndÃ¼z %28,4/gece %5,8 sÃ¼re azalmasÄ±, iki kontrolÃ¼n dÃ¶rder tekrarÄ±nda kare ve olay eÅŸitliÄŸi, 2.947 uygulama + 32 ilgili CV testi ve kanÄ±t zinciri raporlu. Ä°lk gece aralÄ±k hatasÄ± korunup gÃ¶rÃ¼ntÃ¼ aÃ§Ä±lmadan ikame edildi; aday kodu deÄŸiÅŸmedi. SonuÃ§: docs/TORCH-GRUPLAMA-SONUCLARI.md. GerÃ§ek zaman veya kimlik doÄŸruluÄŸu tamamlanmÄ±ÅŸ sayÄ±lmaz.

- [x] Codex kamera: ayrÄ± top ROI modelini yoÄŸun gÃ¶zlem ve yeni gÃ¼ndÃ¼z/gece kontrolleriyle sÄ±nayÄ±p varsayÄ±lan kararÄ±nÄ± ver. (6567f89; kontrol 7fa50fa)
  Done when: gerÃ§ek iki kol/iki tekrar, bÃ¼tÃ¼nlÃ¼k ve ayrÄ±ntÄ±lÄ± top/oyuncu eÅŸitliÄŸi raporlu. GÃ¼ndÃ¼z iki son kare farklÄ± olduÄŸu iÃ§in varsayÄ±lan kapalÄ±; gece Ã§Ä±ktÄ± eÅŸit fakat hÄ±z artmadÄ±. SonuÃ§: docs/ROI-GRUPLAMA-SONUCLARI.md. AÃ§Ä±k deneysel seÃ§im video/canlÄ± yollarÄ±nda korunur.

- [x] Codex kamera: genel/spor OSNet, GTA kÄ±sa parÃ§a baÄŸlantÄ±sÄ±, optik akÄ±ÅŸ ve mevcut palet desteÄŸini tÃ¼m eski ayrÄ±mlarda Ã¶lÃ§.
  Done when: yedi ayrÄ±mÄ±n tamamÄ±, sabit model/kod kaynaklarÄ±, negatif bulgular, hareket gÃ¶rselleri ve 15 kesit Ã¶nbellek tanÄ±sÄ± raporlu. RGB palet adayÄ± altÄ± doÄŸru ayrÄ±mÄ± koruyup beyaz 6 yanlÄ±ÅŸ bÃ¶lÃ¼nmesini reddediyor; baÄŸÄ±msÄ±z kontrol baÅŸarÄ±sÄ± deÄŸildir. SonuÃ§: docs/KIMLIK-GORUNUS-TANISI.md; toplu durum: docs/TAKIP-ENTEGRASYON-DURUMU.md.

- [ ] Codex kamera: kontrolde gÃ¶rÃ¼len beyaz 6 numara yanlÄ±ÅŸ bÃ¶lÃ¼nmesini geliÅŸtirme senaryosuna baÄŸla; gÃ¶rÃ¼nÃ¼ÅŸ/renk/hareket desteÄŸini tÃ¼m ayrÄ±mlarda karÅŸÄ±laÅŸtÄ±r.
  Done when: yanlÄ±ÅŸ ayrÄ±mÄ±n kaynak/karar izi aÃ§Ä±klanÄ±r, alternatif yalnÄ±z geliÅŸtirmede seÃ§ilir; hÄ±z ve kutu/kimlik/takÄ±m kapsamÄ± Ã¶lÃ§Ã¼lÃ¼r, sonraki aday yeni kontrolden geÃ§meden varsayÄ±lan olmaz. Ã–nceki aday dÃ¶rt kontrolde Ã¼Ã§ doÄŸru/bir yanlÄ±ÅŸ ayrÄ±m Ã¼retti ve reddedildi. SonuÃ§: docs/KIMLIK-UZLASISI-KONTROL-SONUCLARI.md.

- [x] Codex kamera: kaybolan iki gÃ¼ndÃ¼z kimlik baÄŸlantÄ±sÄ±nÄ± gÃ¶rÃ¼ntÃ¼/karar iziyle ayÄ±r ve tekrarlanabilir regresyon senaryolarÄ±na baÄŸla. (f31e088)
  Done when: 407 kaynak Ã¶rnek karesinden iki hata yeniden Ã¼retildi; gÃ¶rÃ¼ntÃ¼/karar izi ve dÃ¶rt tanÄ± kolu kaydedildi. 17 yeni test, eski korumalarla birlikte 63 test geÃ§ti. SonuÃ§: docs/KIMLIK-HATA-DENETIMI-SONUCLARI.md. Beyazda parÃ§alÄ± kutu + hareket kapÄ±sÄ±, mavide oyuncu/hakem alt-gÃ¶vde karÄ±ÅŸÄ±mÄ± ayrÄ±ldÄ±. Oracle mÃ¼dahaleleri Ã¼retim dÃ¼zeltmesi deÄŸildir; Ã¼retim kodu deÄŸiÅŸmedi, yeni kontrol aÃ§Ä±lmadÄ±.

- [x] Codex kamera: Deep OC-SORT + OSNet gÃ¶rÃ¼nÃ¼ÅŸ eÅŸleÅŸtirmesini Ã¶lÃ§ ve video/canlÄ± takip motoru seÃ§imine entegre et. (b2310a9)
  Done when: sabit resmÃ® model/kod, 11 kesitte Ã¼Ã§ kol, video/sÄ±cak/izole canlÄ± seÃ§im, 22 birebir eski Ã§Ä±ktÄ± ve 164.772 kiÅŸi gÃ¶zlemi; 95 ilgili CV testi ve 2.893 uygulama testi geÃ§ti. SonuÃ§: docs/TAKIP-REID-SONUCLARI.md. ReID bazÄ± kiÅŸi Ã§iftlerini iyileÅŸtirdi, fakat iki eski doÄŸru gÃ¼ndÃ¼z baÄŸlantÄ±sÄ±nÄ± kaybetti ve bazÄ± forma hatalarÄ±nÄ± artÄ±rdÄ±; deneysel aÃ§Ä±k seÃ§imle entegre, varsayÄ±lan ByteTrack korundu, yeni kontrol aÃ§Ä±lmadÄ±.

- [x] Codex kamera: aÃ§Ä±k kaynak ByteTrack/BoT-SORT/OC-SORT motorlarÄ±nÄ± aynÄ± tespitlerde karÅŸÄ±laÅŸtÄ±r; Deep OC-SORT uyumluluÄŸunu incele. (3eb023b)
  Done when: 11 kesit, motor baÅŸÄ±na 4.125 kare, 44 birebir tekrar; kiÅŸi/forma/kapsam ve sÃ¼re Ã¶lÃ§Ã¼mleri, 65 ilgili CV testi, 2.882 uygulama testi ve PR kontrolleri tamamlandÄ±. SonuÃ§: docs/TAKIP-MOTORU-KARSILASTIRMA-SONUCLARI.md. HiÃ§bir alternatif tÃ¼m geliÅŸtirme kapÄ±larÄ±nÄ± geÃ§medi; Ã¼retim motoru korundu, yeni kontrol aÃ§Ä±lmadÄ±. Deep OC-SORT'un kaynak/CUDA uyumu incelendi; ReID Ã§Ä±karÄ±mÄ± henÃ¼z Ã¶lÃ§Ã¼lmedi.

- [x] Codex kamera: kiÅŸi kimliÄŸi/forma zincirini ortak Ã¼retim akÄ±ÅŸÄ±nda dÃ¼zelt; mÃ¼kerrer parÃ§alarÄ±, kimlik devrini, gÃ¼venli baÄŸlantÄ±yÄ± ve canlÄ± segment kimliklerini birlikte doÄŸrula. (401adb3, 9f571a3, 8a66672)
  Done when: deÄŸiÅŸmez kutularla Ã¼retim tekrarÄ±, kiÅŸi baÄŸlantÄ±sÄ± denetimi, dondurulmuÅŸ kontrol, video/canlÄ±/Ã¶nizleme ve bÃ¼tÃ¼n PR kontrolleri tamamlandÄ±. 2.877 uygulama, 164 ilgili CV ve gerÃ§ek PostgreSQL'de 14 test geÃ§ti. SonuÃ§: docs/SABIT-KAMERA-KIMLIK-SONUCLARI.md. GÃ¼ndÃ¼z kontrolÃ¼nde aynÄ± kiÅŸi baÄŸlantÄ±sÄ± 92/134â†’90/134 gerilediÄŸi iÃ§in deneysel profil otomatik aÃ§Ä±lmadÄ±; gÃ¼ndÃ¼z kontrolÃ¼nÃ¼n baÄŸÄ±msÄ±zlÄ±k sÄ±nÄ±rlarÄ± raporlu, genel kiÅŸi kimliÄŸi doÄŸruluÄŸu tamamlanmÄ±ÅŸ sayÄ±lmaz.

- [x] Codex kamera: kesme/tekrar/kalibrasyon boÅŸluÄŸunda kimlik ve forma geÃ§miÅŸini ayÄ±r, Ã§ekimler arasÄ± hÄ±z hesabÄ±nÄ± kes; takip sÃ¼resini aynÄ± tespitlerde Ã¶lÃ§. (76797ec)
  Done when: 13 gerÃ§ek CV/Ã§ekirdek testi, 87 ilgili uygulama testi, 2.635 tam yerel test; Ã¼retim yolunda 1.125 sabit kamera karesinin oyuncu/renk geÃ§miÅŸi eÅŸit. SonuÃ§: docs/TAKIP-SUREKLILIGI-SONUCLARI.md. Daha uzun bekleme gÃ¼ndÃ¼z doÄŸruyu 195â†’194 dÃ¼ÅŸÃ¼rÃ¼p karÄ±ÅŸÄ±k ID'yi 7â†’8 artÄ±rdÄ±ÄŸÄ± iÃ§in reddedildi; gerÃ§ek sÃ¼re raporlanÄ±yor. Sabit kamerada oyuncular arasÄ± ID deÄŸiÅŸimi ve genel forma/olay doÄŸruluÄŸu tamamlanmÄ±ÅŸ sayÄ±lmaz.

- [x] Codex kamera: saha Ã§evresindeki sahte takipleri ayÄ±r, kamera bazÄ±nda doÄŸrula ve Ã¶nizleme zaman/boyut/geometri hatalarÄ±nÄ± dÃ¼zelt. (a9079c1)
  Done when: dondurulmuÅŸ filtre, 248 yeni kÃ¶r kontrol kutusu, iki yeni gece klibi, gerÃ§ek dedektÃ¶r tekrarÄ±nda 375 karenin birebir eÅŸleÅŸmesi ve okunabilir Ã¶nizleme. SonuÃ§: docs/OYUNCU-SUZGECI-SONUCLARI.md. GÃ¼ndÃ¼z 25 sahte kutuâ†’0, forma kaybÄ± 0, doÄŸru 83â†’95; gece ek baÅŸka-renk atamasÄ± nedeniyle yalnÄ±z 117093 profili etkin. 89 ilgili test geÃ§ti; genel doÄŸruluk/oyuncu kimliÄŸi/olay doÄŸruluÄŸu tamamlanmÄ±ÅŸ sayÄ±lmaz.

- [x] Codex kamera: aydÄ±nlÄ±k 117093 maÃ§Ä±nÄ± ayrÄ± kalibrasyonla iÅŸle, kÃ¶r dÄ±ÅŸ kontrolÃ¼ Ã¶lÃ§ ve baÅŸarÄ±sÄ±z Ä±ÅŸÄ±k varsayÄ±lanÄ±nÄ± geri al. (417b25e)
  Done when: Ã¼Ã§ kaynak klip/hash, 172 kutu etiketi, 65 saha iÅŸareti, aynÄ± kutularda ham/Ã§im karÅŸÄ±laÅŸtÄ±rmasÄ±, Ã¼retim yolu eÅŸitliÄŸi ve takip Ã¶nizlemesi hazÄ±r. SonuÃ§: docs/GUNDUZ-MACI-SONUCLARI.md; kontrol ham 53/13/8, Ã§im 16/54/4 (doÄŸru/yanlÄ±ÅŸ/atanamayan). Ham varsayÄ±lan, normalizasyon aÃ§Ä±k seÃ§imle korunur. 29 ilgili ve 2.594 tam yerel test geÃ§ti, 1 atlandÄ±. KiÅŸi olmayan tespit ve olay doÄŸruluÄŸu Ã§Ã¶zÃ¼lmÃ¼ÅŸ sayÄ±lmaz.

- [x] Codex kamera: gÃ¶lge dÃ¼zeltmesini yeni kontrol klipleriyle yeniden dene ve geÃ§en yerel Ã§im normalizasyonunu takip hattÄ±na baÄŸla. (93d2413)
  Done when: iki ayrÄ± dondurulmuÅŸ deney, yeni 149 kÃ¶r kutu etiketi, Ã¼retim fonksiyonuyla 54.103 gÃ¶zlemin aynÄ± sonucu vermesi, video/canlÄ± entegrasyonu ve regresyonlar. SonuÃ§: docs/YEREL-CIM-ISIGI-SONUCLARI.md; yeni kontrol 54â†’56 doÄŸru, 7â†’4 yanlÄ±ÅŸ, 5â†’6 atanamayan. 80 ilgili ve 2.569 tam yerel test geÃ§ti; 1 atlandÄ±. Genel maÃ§lar arasÄ± doÄŸruluk hedefi tamamlanmÄ±ÅŸ sayÄ±lmaz.

- [x] Codex kamera: gÃ¶lgeli forma iÃ§in doÄŸrudan gÃ¶rÃ¼ntÃ¼ etiketleriyle medyan/parlak dÃ¶rtte birlik deneyini dondurulmuÅŸ kontrolde Ã¶lÃ§. (943d411)
  Done when: tahminden baÄŸÄ±msÄ±z 142 kutu, kÃ¶r gÃ¶rÃ¼ntÃ¼ incelemesi, geliÅŸtirme/kontrol ayrÄ±mÄ± ve kabul regresyonlarÄ±. SonuÃ§: docs/GOLGE-FORMA-SONUCLARI.md; 58 ilgili test geÃ§ti. GeliÅŸtirme 36â†’41 doÄŸru, kontrol 66â†’65 doÄŸru; aday Ã¼retime alÄ±nmadÄ±. Otomatik PR tamamlama yetkisi AGENTS.md'de kayÄ±tlÄ± (f7baf5b).

- [x] Codex kamera: konumsal takÄ±m uyuÅŸmazlÄ±klarÄ±nÄ± gÃ¶rÃ¼ntÃ¼ kanÄ±tÄ±yla ayÄ±r ve tekrar Ã¼retilebilir hata tanÄ±sÄ± ekle. (407a565)
  Done when: geliÅŸtirme/kontrol tanÄ±sÄ±, kaynak kutu gÃ¶rÃ¼ntÃ¼leri ve gÃ¶rsel inceleme notlarÄ±, anlamlÄ± regresyonlar ve lint/tip kontrolÃ¼. SonuÃ§: docs/TAKIM-HATA-TANISI-SONUCLARI.md; 49 ilgili test geÃ§ti. %81,11 ve 119 uyuÅŸmazlÄ±k gerÃ§ek forma doÄŸruluÄŸu/hata sayÄ±sÄ± olarak kullanÄ±lamaz; model deÄŸiÅŸmedi.

- [x] Codex kamera: ayÄ±rt edilemeyen forma renklerinden takÄ±m Ã¼retmeyi ve geÃ§ersiz canlÄ± renk Ã§apasÄ±nÄ± Ã¶nle. (b52767e)
  Done when: tek renk/canlÄ± geÃ§iÅŸ regresyonlarÄ±, aynÄ± geliÅŸtirme-kontrol kayÄ±tlarÄ±nda Ã¶lÃ§Ã¼m ve tam test/lint/tip kontrolÃ¼. SonuÃ§: docs/TAKIM-RENK-BELIRSIZLIGI-SONUCLARI.md; 2529 test geÃ§ti. Kontrol doÄŸruluÄŸu %81,11 kaldÄ±; genel doÄŸruluk hedefi henÃ¼z geÃ§ilmedi.

- [x] Karne incelemesi: yetersiz bayrakla baÅŸarÄ± hÃ¼kmÃ¼nÃ¼ ve aynÄ± dakikadaki oyuncu sayÄ±mÄ±nÄ± dÃ¼zelt; Ã¶zgÃ¼n veride yeniden Ã¶lÃ§. (8c7b938)
  Done when: regresyonlar ve birleÅŸik testler temiz, 100 maÃ§lÄ±k Ã¶zgÃ¼n girdi SHA-256 ile eÅŸleÅŸir, yeni Ã¶lÃ§Ã¼m ve sÄ±nÄ±rlar raporlanÄ±r. SonuÃ§: docs/KARNE-DUZELTME-SONUCLARI.md.

- [x] Top adaylarÄ±nÄ±, oyuncu Ã§evresi ROI aramasÄ±nÄ± ve saha Ã§izgisi kalibrasyonunu dondurulmuÅŸ kontrolle karÅŸÄ±laÅŸtÄ±r; farklÄ± piksel boyutunda kalibrasyonu reddet. (4b8d149)
  Done when: aynÄ± tam kare tespitleriyle tekrar takip, Ã§izgi/pas/takÄ±m Ã¶lÃ§Ã¼mleri ve baÅŸarÄ±sÄ±z deney raporu; test/lint/tip kontrolleri temiz. SonuÃ§: docs/TOP-SECIMI-SONUCLARI.md. Alternatifler doÄŸruluk kapÄ±sÄ±nÄ± geÃ§medi; varsayÄ±lanlar deÄŸiÅŸtirilmedi.

- [x] Video top/pas/top kazanÄ±mÄ± kanÄ±t zincirini dÃ¼zelt; yoÄŸun kare denemesini ve gerÃ§ek olay eÅŸleÅŸmesini Ã¶lÃ§. (b1eb581)
  Done when: kamera/zaman/top belirsizliÄŸi korunur; video/canlÄ± JSONâ†’DBâ†’domain zinciri ve kÄ±smi savunma korumasÄ± testli; birebir GT karÅŸÄ±laÅŸtÄ±rmasÄ± ve baÅŸarÄ±sÄ±z deneyler raporlu. SonuÃ§: docs/VIDEO-OLAY-SONUCLARI.md. Pas duyarlÄ±lÄ±ÄŸÄ± ve gerÃ§ek gÃ¶rÃ¼ntÃ¼de savunma doÄŸruluÄŸu hedefleri geÃ§ilmedi; yoÄŸun olay akÄ±ÅŸÄ± varsayÄ±lan kapalÄ±.

- [x] Sabit kamera: takÄ±m renklerine sÄ±zan kÄ±sa takipleri/farklÄ± renkleri ele ve GT ile Ã¶lÃ§. (8ae76c3)
  Done when: aynÄ± gÃ¶zlemlerle geliÅŸtirme/kontrol karÅŸÄ±laÅŸtÄ±rmasÄ±, oyuncu kaybÄ± ve pas/savunma baÅŸlangÄ±Ã§ raporu; test/lint/tip kontrolleri temiz. Kapsam: docs/SABIT-KAMERA-SINYAL-PLANI.md.

- [x] Mobile sidebar drawer  (ba07618)
  Done when: drawer opens/closes on mobile breakpoints, nav items reachable, tsc+build clean, committed.
- [x] Decisions API load-perf cache  (b2c55d6)
  Done when: /decisions endpoints cached with sane TTL, repeat-load latency measurably lower, tests cover cache hit/miss, committed.
- [x] End-to-end smoke run â€” La Liga match  (bc44854)
  Done when: full decision flow (live â†’ apply â†’ track â†’ reconcile) runs green on a La Liga fixture in demo mode, no console errors, committed.

-----

## Next (pull these once "Now" is clear)

- [x] return_to_play engine  (ceec769)
  Done when: engine implemented in engine layer, wired apiâ†’aiâ†’engineâ†’domain, unit tests green, committed.
- [x] minutes_management engine  (8a9f839)
  Done when: as above.
- [x] congestion_risk engine  (a94952d)
  Done when: as above.
- [x] weekly_digest output motor  (3951a49)
  Done when: generates digest from real engine outputs, rendered in UI, tested, committed.
- [x] prematch_brief output motor  (b2083cf)
  Done when: as above.

-----

## Later (lower priority â€” only if Now + Next clear)

- [ ] PDF report export for scout_report_generator
- [ ] Push/email delivery for digests (currently pull-only)
- [ ] i18n scaffold for English UI
- [x] Security headers (CSP / HSTS / X-Frame-Options / X-Content-Type-Options)  (b067175)
- [x] Retry + circuit-breaker on external API calls  (868f289)
- [x] Liveness/readiness split on /health  (pre-existing â€” /healthz + /readyz)

-----

## Done (archive â€” keep last ~10 for context)

- [x] LiveDecisionDigestAgent â†’ AI brief paneli  (5b36b56, PR #193)
- [x] Video clip stub + PWA offline shell + pilot pitch  (97d6eba, PR #192)
- [x] Audit fixes â€” replay commit + docs eksikleri  (dd08676, PR #191)
- [x] 3 yeni engine (hot_hand/set_piece/referee) + La Liga smoke  (d2da3d1, PR #190)
- [x] Decisions UI cilasÄ± â€” hub tiles + tooltipler + Karar YansÄ±t  (9f6646b, PR #189)
- [x] Closing/foul/star engines + frontend + ingest derinliÄŸi  (cad18bc, PR #188)

-----

## Notes / blockers (anything needing human eyes)

- (none currently)
- [x] DedektÃ¶r v2'yi Ã¼retime al (kullanÄ±cÄ± kararÄ± 2026-11-01): canli_mac sabit kamera + API varsayÄ±lanÄ±.
- [x] Top tespiti: olay tabanlÄ± Ã¶lÃ§Ã¼m + aday izi, Ã¶n kayÄ±tlÄ± kontrol 6/6 geÃ§ti (feat/top-izi).
- [x] Top: gÃ¼ndÃ¼z maÃ§Ä±nda doÄŸrulama â€” 132877, Ã¶n kayÄ±tlÄ± 5/5 geÃ§ti (test/gunduz-132877).
- [x] Top: veritabanÄ±na giden karelere de aday izini uygula (telestrasyon iÅŸÃ§isi takip aktarÄ±mÄ±ndan sonra gÃ¼nceller; fix/panel-gercek-mod).
- [x] Top: paslarÄ± dÃ¼zeltilmiÅŸ topla yeniden tÃ¼retme â€” iki Ã¶n kayÄ±tlÄ± sÄ±nav geÃ§medi (kesinlik âˆ’8, savunan takÄ±m âˆ’4/âˆ’22); baÄŸlanmadÄ± (TOP-TESPITI-OLAY-OLCUMU Â§7).
- [ ] Pas motoru: gecede duyarlÄ±lÄ±k ~%0â€“15; top gÃ¶rÃ¼nÃ¼rlÃ¼ÄŸÃ¼ sÄ±nÄ±rÄ± â€” kare baÅŸÄ±na top GT'li yeni veriyle tasarÄ±m.
- [x] Panel gerÃ§ek modda doÄŸrulandÄ±: CanlÄ± Telestrasyon kartÄ± videoyu gÃ¶steriyor; genel bakÄ±ÅŸtaki yanlÄ±ÅŸ 'backend baÄŸlÄ± deÄŸil' uyarÄ±sÄ± dÃ¼zeltildi.
- [x] TakÄ±m atamasÄ±, renk oranÄ±yla yeniden atama: Ã¶n kayÄ±tlÄ± kontrol 1/4 â€” GEÃ‡MEDÄ°, canlÄ±ya baÄŸlanmadÄ±; Ã¼retim net renkte %93â€“97 doÄŸru (docs/TAKIM-AYRIMI-GUNES.md).
- [x] TakÄ±m: 132831 GSR'ye karÅŸÄ± Ã¶lÃ§Ã¼ldÃ¼ â€” takÄ±m uyumu %76,7; sÄ±nÄ±r tespit/konum (9,1 eÅŸleÅŸen oyuncu/kare, 3,4 m).
- [x] Yeni sahada tespit kapsamasÄ±: 132831 MOT klibinde v2 %96,1 â€” tespit sorun deÄŸil; dÃ¼ÅŸÃ¼k GSR eÅŸleÅŸmesi referans geometrisi (2â€“3 m en kaymasÄ±).
- [x] GSRâ€“kalibrasyon 2â€“3 m en kaymasÄ± Ã§Ã¶zÃ¼ldÃ¼: resmÃ® saha iÅŸaretlerine karÅŸÄ± GSR dÃ¶nÃ¼ÅŸÃ¼mÃ¼ 5â€“9 m sapÄ±yor, bizimki 1,5 m â†’ kayma GSR tarafÄ±nda (gsr-reference-geometry.json).
- [x] GSR referansÄ± saha iÅŸaretlerine gÃ¶re dÃ¼zeltildi (correct_gsr_positions); gÃ¼ndÃ¼z ve Ã¼Ã§Ã¼ncÃ¼ saha karnesi yeniden hesaplandÄ±. Gece (117092) GSR gÃ¶rÃ¼ntÃ¼sÃ¼ panorama kÄ±rpÄ±mÄ± deÄŸil â€” dÃ¼zeltilemedi.
- [ ] Aday izi 132831'de yanlÄ±ÅŸ topu +5 puan artÄ±rdÄ± (Ã¶n kayÄ±tlÄ± sÄ±nÄ±r +2): yeni sahada adaylarÄ± seÃ§icilik ayarÄ±, yeni Ã¶n kayÄ±tla.
- [ ] Aday izi sonrasÄ± aktÃ¶r/sahip alanlarÄ± eski topta kalÄ±yor (veri tutarlÄ±lÄ±ÄŸÄ±; Ã¶lÃ§Ã¼len etki yok).
- [x] Åekil bekÃ§isi eÅŸikleri referansa karÅŸÄ± Ã¶lÃ§Ã¼ldÃ¼: blok 6 m ve hat aralÄ±ÄŸÄ± 4 m gÃ¼ndÃ¼z gÃ¼venilir, gecede sÄ±nÄ±rda; geniÅŸlik 6 m ve boy 6 m gÃ¼rÃ¼ltÃ¼ iÃ§inde (SEKIL-BEKCISI-OLCUMU.md).
- [ ] (diÄŸer oturum) geniÅŸlik â†’ %10â€“90 aralÄ±ÄŸÄ± + eÅŸik 8 m; boy â†’ p90 derinlik âˆ’ geri hat; hat aralÄ±ÄŸÄ± eÅŸiÄŸi 5 m; sonra aynÄ± araÃ§la yeniden Ã¶lÃ§.
- [x] USB kamera (Insta360 X5) ile canlÄ± hat ilk koÅŸu: segment/dedektÃ¶r/DB Ã¶n kontrolÃ¼ tamam; sahasÄ±z gÃ¶rÃ¼ntÃ¼de kare yazÄ±lmaz (otomatik Ã§apa bulunamaz, doÄŸru davranÄ±ÅŸ) â€” docs/measurements/live-rehearsal-990771-usb-camera.json
- [x] Saha gÃ¼nÃ¼ Ã¶n kontrolÃ¼ `scripts/saha_hazirlik.py`: ffmpeg/kamera kipleri/disk bÃ¼tÃ§esi/GPU/DB/kalibrasyon tek komutta GEÃ‡TÄ°-UYARI-KALDI; Ã§Ä±kÄ±ÅŸ kodu 0/1/2 â€” docs/CANLI-MOD-KILAVUZU.md Â§0
- [x] VLSC U19 (CC BY) operatÃ¶rlÃ¼ kamera provasÄ±, PR #221 kapÄ±larÄ±yla: 0 kare (3 segment, Ã§apa karesi dahil); Ã§apa kendi karesinde %37, iyileÅŸtirme en Ã§ok %57 < %85 â€” Ã§izgi Ã§Ä±karÄ±cÄ± Ã§it korkuluÄŸunu taÃ§ Ã§izgisi sanÄ±yor, yakÄ±n yarÄ± Ã§izgileri Ã§Ä±kmÄ±yor; EylÃ¼l'deki %91 bozuk kalibrasyon koduyla alÄ±nmÄ±ÅŸtÄ±, geÃ§ersiz â€” docs/measurements/live-rehearsal-990774-vlsc-operated.json
- [x] Ã‡izgi Ã§Ä±karÄ±mÄ± adayÄ± (yerel kontrast + doyma bekÃ§isi) gÃ¼ndÃ¼z Ã¶lÃ§Ã¼ldÃ¼, ÃœRETÄ°ME ALINMADI: J.League Ã§apa karesi inlier %47 â†’ %63, VLSC %37 â†’ %52, ama uÃ§tan uca doÄŸrulanabilir kare â‰ˆ0 ve yakÄ±n Ã§ekimde yanlÄ±ÅŸ kabul arttÄ±; `pitch_lines.py` dondurulmuÅŸ kimlik kontrollerinin Ã¶lÃ§tÃ¼ÄŸÃ¼ kod (hash korumalÄ±) â€” docs/measurements/line-extraction-daylight-2026-11-02.json
- [ ] GÃ¼ndÃ¼z kalibrasyon: gece bench tablosu (README) gÃ¼ndÃ¼zde geÃ§ersiz; gÃ¼ndÃ¼z sabit kamera + DOÄRU kalibrasyonlu bir kaynakla bench yeniden kurulmalÄ± (bench_day'in 117093 landmarks gerÃ§ek-deÄŸeri 1,43 m, kullanÄ±lamaz)
- [ ] Ã‡im maskesi aÄŸaÃ§ Ã¶rtÃ¼sÃ¼nÃ¼ iÃ§ine alÄ±yor (VLSC): aday Ã§Ä±karÄ±cÄ±da maske doyup bekÃ§iyi tetikliyor â†’ saha bÃ¶lgesi iÃ§in doku/erozyon ayrÄ±mÄ±; Ã¶lÃ§Ã¼t VLSC 60 s Ã§apa inlier (aday: bekÃ§i â†’ 0)
- [ ] ENGEL â€” yayÄ±n (hareketli kamera) yolu profesyonel GÃœNDÃœZ yayÄ±nÄ±nda Ã§alÄ±ÅŸmÄ±yor (J.League 6 dk, 5395 kare): otomatik Ã§apa 0/326; elle Ã§apayla doÄŸrulanabilir kare â‰ˆ0, buna karÅŸÄ±lÄ±k yakÄ±n Ã§ekim / kale kamerasÄ±nda YANLIÅ KABUL (eski Ã§Ä±karÄ±cÄ± 356 s yÃ¼z yakÄ±n Ã§ekimi %100 inlier; yeni 38â€“207 s kale yakÄ±n Ã§ekimleri %86). KapÄ± tasarÄ±mÄ±: kesme/kamera deÄŸiÅŸiminde az model noktalÄ± karede inlier anlamsÄ±z â†’ kadraj iÃ§i gÃ¶rÃ¼nÃ¼r nokta + kapsama + kesme tespiti birlikte; PR #221'in gece sentetik "0 yanlÄ±ÅŸ kabul"u gÃ¼ndÃ¼ze taÅŸÄ±nmÄ±yor â€” docs/measurements/line-extraction-daylight-2026-11-02.json
- [x] YayÄ±n Ã§apasÄ± kÃ¶r kontrolÃ¼ KALDI, Ã¼retime BAÄLANMADI: main 51/172 = %29,7 (ÅŸart %30, 52 gerekiyordu); medyan hata 0,93 m, yanlÄ±ÅŸ >5 m 1/25, other 2/68 tuttu. chiba_tokushima ve kashiwa_machida gÃ¶rÃ¼ldÃ¼, yeni deneme yeni maÃ§ ister. Takip kaybÄ± (3/675) aÃ§Ä±k â€” docs/measurements/broadcast-anchor-control-result.json
- [x] YayÄ±n takibi kÃ¶r kontrolÃ¼ KALDI, Ã¼retime BAÄLANMADI: main 79/159 = %49,7 (ÅŸart %50, 80 gerekiyordu); 30 iÅŸaretli Ã¼retimde medyan 0,37 m, kare medyanÄ± >5 m yok, other 0/81 tuttu. hiroshima_kyoto ve kashiwa_hiroshima_final gÃ¶rÃ¼ldÃ¼, yeni deneme yeni maÃ§ ister â€” docs/measurements/broadcast-track-control-result.json
- [x] YayÄ±n takibi 4. tur kÃ¶r kontrolÃ¼ GEÃ‡TÄ°, Ã¼retime BAÄLANMADI: main 82/101 = %81,2 (ÅŸart %50), en dÃ¼ÅŸÃ¼k maÃ§ kashima_machida_2024 22/34 = %64,7; 42 iÅŸaretli Ã¼retimde medyan 0,40 m, kare medyanÄ± >5 m yok, other 1/139. Ä°ki maÃ§, 6ÅŸar dakika, yalnÄ±z maÃ§ sonrasÄ±; kashima_machida_2024 ve kobe_shonan_2024 gÃ¶rÃ¼ldÃ¼ â€” docs/measurements/broadcast-track-round4-control-result.json
- [x] YayÄ±n takibi maÃ§ sonrasÄ± hatta baÄŸlama, parÃ§a 1 (hÄ±z): kamera Ã¶nseli Ä±zgarasÄ±nÄ±n izdÃ¼ÅŸÃ¼mÃ¼ kare baÅŸÄ±na deÄŸil bir kez hesaplanÄ±r (`camera_anchor.grid_index`). Ä°ki kontrol kesitinde ikinci geÃ§iÅŸ Ã§Ä±ktÄ±sÄ± birebir aynÄ± (states, samples, poses); sÃ¼re kashima_machida_2024 2618 â†’ 1171 sn, kobe_shonan_2024 1656 â†’ 916 sn (ikisi aynÄ± anda koÅŸarken). SÄ±nÄ±r: 6 dk'lÄ±k kesit iki geÃ§iÅŸle hÃ¢lÃ¢ ~25 dk; tam maÃ§ ~6 saat.
- [x] YayÄ±n takibi maÃ§ sonrasÄ± hatta baÄŸlama, parÃ§a 2: iki geÃ§iÅŸ + bekÃ§i tek giriÅŸ noktasÄ± `app/tracking/broadcast_two_pass.track_two_pass`; Ã§apa `BackfillingTracker(anchor=...)` ile verilir, modÃ¼l yamalanmaz. Ä°ki kontrol kesitinde Ã¶rnek karelerdeki duruÅŸlar ve kare durumlarÄ± kontrol kaydÄ±yla birebir aynÄ± (23 ve 60 duruÅŸ). Ä°ki geÃ§iÅŸ birlikte 1654 ve 1494 sn (aynÄ± anda koÅŸarken). SÄ±nÄ±r: video iki kez okunur; kamera konumu 3 sn'de bir duruÅŸtan bulunur (kontroldeki Ã¶rnekleme).
- [x] YayÄ±n takibi maÃ§ sonrasÄ± hatta baÄŸlama, parÃ§a 3: `scripts/track_video_product.py --broadcast-two-pass` (`scripts/track_video.py` hash'le dondurulmuÅŸ, kip oraya yazÄ±lmadÄ±; parÃ§alÄ± iÅŸÃ§i argÃ¼manÄ± aynen geÃ§irir). DuruÅŸlar hat koÅŸmadan Ã¶nce bulunur ve hatta kalibratÃ¶r olarak verilir (`app/tracking/broadcast_calibrator.py`); dondurulmuÅŸ hat koduna dokunulmadÄ±, kip istenmedikÃ§e davranÄ±ÅŸ aynÄ±. UÃ§tan uca: kobe_shonan_2024 ilk 90 sn â†’ 1349 karenin 533'Ã¼ duruÅŸlu (%39,5; diÄŸer kameralar dahil), bekÃ§i 86 duruÅŸ attÄ±, 170 Ã§Ä±ktÄ± karesi, kare baÅŸÄ±na 14,1 oyuncu; hat 85 sn sÃ¼rdÃ¼, iki geÃ§iÅŸin sÃ¼resi bu koÅŸuda Ã¶lÃ§Ã¼lmedi. Ã–lÃ§Ã¼lmeyen: oyuncu konumlarÄ±nÄ±n doÄŸruluÄŸu (yalnÄ±z duruÅŸ doÄŸruluÄŸu kÃ¶r kontrolde Ã¶lÃ§Ã¼ldÃ¼).
- [x] YayÄ±n iki geÃ§iÅŸ kipi, tekrar sÃ¼zme: ilk geÃ§iÅŸin tekrar saydÄ±ÄŸÄ± (kÄ±rmÄ±zÄ± J.League logo geÃ§iÅŸi) karede duruÅŸ Ã¼retilmez; kapanÄ±ÅŸ geÃ§iÅŸi gÃ¶rÃ¼lmeyen pencerede (izleyicinin 60 sn tavanÄ±na dayanan) duruÅŸ atÄ±lmaz, pencere Ã¶zette `replay_unclosed_windows_s` ile bildirilir. Ã–lÃ§Ã¼m (iki gÃ¼ndÃ¼z kesiti, 6'ÅŸar dk): kobe_shonan 3 pencere, atÄ±lan duruÅŸ 0 (2629 â†’ 2629); kashima_machida 2 kapalÄ± pencere, atÄ±lan duruÅŸ 3 (1083 â†’ 1080), 1 kapanmamÄ±ÅŸ pencere (80â€“140. sn). KapanmamÄ±ÅŸ pencere kuralÄ± olmadan kashima'da 188 duruÅŸ atÄ±lÄ±yordu; Ã¶rnek karelerde atÄ±lan 4 duruÅŸun dÃ¶rdÃ¼ de (105, 108, 135, 138. sn) canlÄ± oyundu: kapanÄ±ÅŸ geÃ§iÅŸi kÄ±rmÄ±zÄ± formalÄ± yakÄ±n Ã§ekimle birleÅŸip (kÄ±rmÄ±zÄ± dilim 4 sn, sÄ±nÄ±r 1,2 sn) kaÃ§Ä±yor. SÄ±nÄ±r: atÄ±lan 3 karenin gerÃ§ekten tekrar olduÄŸuna tek tek bakÄ±lmadÄ±; bu iki kesitte duruÅŸlu ana kamera tekrarÄ± neredeyse yok, sÃ¼zgecin yararÄ± bu veriyle gÃ¶sterilemedi.
- [ ] YayÄ±n tekrar izleyici: kapanÄ±ÅŸ geÃ§iÅŸi kÄ±rmÄ±zÄ± iÃ§erikle birleÅŸince kaÃ§Ä±yor (kashima_machida 89â€“93. sn); o pencere sÃ¼zÃ¼lmeden kalÄ±yor ve ilk geÃ§iÅŸte (kamera bulma) 60 sn canlÄ± oyun tekrar sayÄ±lÄ±yor. `shot_filter.py` dondurulmuÅŸ; yeni geÃ§iÅŸ kuralÄ± ayrÄ± modÃ¼lde ve yeni maÃ§larla Ã¶n kayÄ±tlÄ± Ã¶lÃ§Ã¼lmeli. Ä°ÅŸaret yalnÄ±z J.League yayÄ±nÄ±na Ã¶zgÃ¼. Done when: kÄ±rmÄ±zÄ± formalÄ± en az 2 yeni gÃ¼ndÃ¼z maÃ§Ä±nda kaÃ§an geÃ§iÅŸ sayÄ±sÄ± Ã¶lÃ§Ã¼lÃ¼r ve kural ya dÃ¼zeltilir ya da bÄ±rakÄ±lÄ±r.
- [ ] YayÄ±n iki geÃ§iÅŸ kipi: kamera konumu kÄ±sa videoda oynuyor (90 sn: 51,0; 104,0; 17,8 â€” 6 dk: 52,1; 107,8; 17,6). Done when: en az video sÃ¼resi Ã¶lÃ§Ã¼lÃ¼p yazÄ±lÄ±r ya da kip kÄ±sa videoyu reddeder.
- [ ] YayÄ±n iki geÃ§iÅŸ kipi: tam maÃ§ koÅŸusu (sÃ¼re, bellek, kapsama) ve 90 sn'de 23 takipÃ§i sÄ±fÄ±rlamasÄ±nÄ±n kimlik sÃ¼rekliliÄŸine etkisi. Done when: bir tam gÃ¼ndÃ¼z maÃ§Ä± uÃ§tan uca koÅŸulur, sayÄ±lar yazÄ±lÄ±r.
- [ ] YayÄ±n takibi 2. tur: uzun kÃ¶prÃ¼ geliÅŸtirmede kaldÄ±, aynÄ± 3 maÃ§ta %66,2 â†’ %60,1, kod geri alÄ±ndÄ±; sonraki adÄ±m kullanÄ±cÄ± kararÄ±nda â€” docs/measurements/broadcast-track-round2-development-result.json
- [ ] YayÄ±n takibi kapsama tanÄ±sÄ±: kayÄ±p %39,4 Ã§apa eksik (maÃ§ farkÄ±nÄ±n ana kaynaÄŸÄ±, 0-26 Ã¶rnek), %50,0 Ã§ekim ayÄ±rÄ±cÄ± + tekrar; filtresiz 3 maÃ§ta %53,8 â†’ %81,3 ama verdy other 4/39; gÃ¶lge aÃ§Ä±klamÄ±yor; taÅŸÄ±nan duruÅŸ aramayÄ± engelliyor (long_search 215/309, long_block 184/309). hiroshima_kyoto ve kashiwa_hiroshima_final artÄ±k geliÅŸtirme verisi, bir daha kontrol olamaz. 3. tur taslaÄŸÄ± kullanÄ±cÄ± onayÄ±nda â€” docs/measurements/broadcast-track-coverage-diagnosis.json
- [ ] YayÄ±n takibi 3. tur: filtre engellemez + sabit kamera bekÃ§isi geliÅŸtirmede kaldÄ±, main 326/468 = %69,7 (ÅŸart %70), kashima_marinos %44,9 (ÅŸart %50), other %2,4; kod geri alÄ±ndÄ±; kullanÄ±cÄ± yÃ¶nÃ¼ Ã¶nce Ã§apa â€” docs/measurements/broadcast-track-round3-development-result.json
- [ ] YayÄ±n Ã§apasÄ± kamera Ã¶nseli geliÅŸtirmede kaldÄ±: takip hattÄ±nda main 280 â†’ 307/468 = %65,6 (ÅŸart %70), other 3/252; kayÄ±plarÄ±n 94/161 filtrelerde, 39 arama bekleme, no_anchor 6; kod geri alÄ±ndÄ±, kontrol aÃ§Ä±lmadÄ± â€” docs/measurements/broadcast-anchor-camera-prior-development-result.json
- [x] Ã‡ekim ayÄ±rÄ±cÄ± kÃ¶r sÄ±navÄ± KALDI, takip hattÄ±na BAÄLANMADI: kontrol (verdy_kashima, niigata_kashiwa) main geÃ§me 95/163 = %58,3 (Wilson %50,6â€“%65,6; Ã¶lÃ§Ã¼t â‰¥%85), other sÄ±zÄ±ntÄ± 4/77 = %5,2 (Wilson %2,0â€“%12,6; Ã¶lÃ§Ã¼t â‰¤%5). GeliÅŸtirme 209/228 ve 1/132 iyimser Ã§Ä±ktÄ±. AynÄ± kontrolle ikinci deneme yok; yeni deneme yeni kontrol maÃ§Ä± ister â€” docs/measurements/shot-exam-control-result.json
- [ ] KapÄ± %85 vs Ã§apa tavanÄ±: elle 6 nokta Ã§apa kadraj dÄ±ÅŸÄ± yakÄ±n tacÄ± iÃ§eri dÃ¼ÅŸÃ¼rÃ¼yor (J.League tavan ~0,70) â†’ operatÃ¶r Ã§apasÄ±nda kadraj iÃ§i nokta zorunluluÄŸu ya da inlier'Ä± yalnÄ±z kadraj iÃ§i GÃ–RÃœNÃœR Ã§izgi noktalarÄ±nda hesaplama; Ã¶lÃ§Ã¼lmeden kapÄ± deÄŸiÅŸmez
- [x] GÃ¼ndÃ¼z panel demosu: 990741 (132877, gÃ¼ndÃ¼z, sabit kamera) telestrasyonla panelde; gece 990731 yerine bu gÃ¶sterilir â€” docs/measurements/panel-daylight-demo-990741.json
- [ ] (diÄŸer oturum) Otomatik hÃ¼cum yÃ¶nÃ¼ gÃ¼ndÃ¼z 990741'de karelerin %71'ini kesiyor (Ã§izilen %29; bilinen yÃ¶nle %100): canlÄ± baÅŸlangÄ±Ã§ta operatÃ¶r yÃ¶n seÃ§imi (`--home-attack` panele) ya da otomatik yÃ¶nÃ¼n doÄŸruluÄŸunu Ã¶lÃ§Ã¼p kapÄ±yÄ± dÃ¼zeltme
- [ ] (diÄŸer oturum) Panelde AI brief ve kapanÄ±ÅŸ reÃ§etesi kaydÄ±rÄ±cÄ±dan 80' okuyor, telestrasyon 19,5': aynÄ± ekranda iki maÃ§ anÄ±; canlÄ± modda hepsi takip dakikasÄ±ndan gelmeli; brief hÃ¢lÃ¢ STUB
- [ ] (diÄŸer oturum) decisions/live dakika kaydÄ±rÄ±cÄ±sÄ± 50â€“95: prova maÃ§larÄ± 10â€“45. dakikada, canlÄ± modda dakika takip durumundan (processed_minute) gelmeli; telestrasyon kartÄ± 401'de 'giriÅŸ gerekli' demeli.


### Gece 2026-11-13 (03:00â€“07:00, kullanÄ±cÄ± devretti; kararlar bende) â€” dal exam/urun-tam-mac

- [x] ParÃ§a Ã§Ã¶kmesi: ffmpeg kare-zamanÄ± sÄ±nÄ±rÄ± kimlik ad alanÄ±nÄ± dÃ¼ÅŸÃ¼rÃ¼yordu; baÅŸlangÄ±Ã§ ms'ye yuvarlanÄ±r. (c3ed6ba)
  Done when: gerÃ§ek videoda ikinci parÃ§a ve sonrasÄ± Ã§alÄ±ÅŸÄ±r. (150 sn / 60 sn: 3/3 parÃ§a bitti)
- [x] DondurulmuÅŸ `app/tracking/replay.py` 14eb4b4'te deÄŸiÅŸti, `test_guarded_control` kÄ±rmÄ±zÄ±. Karar: dosyayÄ± dondurulmuÅŸ haline dÃ¶ndÃ¼r, yeniden Ä±sÄ±nmayÄ± ayrÄ± modÃ¼le taÅŸÄ±, Ã¼rÃ¼n iÅŸÃ§isinde baÄŸla.
  Done when: tÃ¼m pytest yeÅŸil, ruff + mypy temiz, davranÄ±ÅŸ testleri yeni modÃ¼le taÅŸÄ±ndÄ±. (1cb311c; 3384 geÃ§ti, 0 kaldÄ±)
- [x] Ä°ÅŸ baÅŸlamadan bellek/disk Ã¶n kontrolÃ¼: yetmiyorsa iÅŸ aÃ§Ä±k sebeple reddedilir.
  Done when: test var; eÅŸik Ã¶lÃ§Ã¼len iÅŸÃ§i isteÄŸine (10 GB commit) dayanÄ±r ve belgelidir. (3d036bb; disk kapÄ±sÄ± parÃ§alÄ± iÅŸlemede zaten vardÄ±)
- [x] PR aÃ§, CI yeÅŸilse birleÅŸtir. (tactic11#354)
- [x] SÄ±nav 3. deneme: 117093 ilk 1800 sn, maÃ§ 990806, iÅŸ 11747bcb4e. KALDI: 7/8 ÅŸart, sÃ¼re oranÄ± 5,307 > 5,0. SonuÃ§ docs/measurements/product-full-match-exam-result-attempt3.json; rapor docs/GECE-RAPORU-2026-11-13.md.
- [ ] El kontrolÃ¼ (kullanÄ±cÄ±): data/tracking/out/el_kontrol_attempt3/ altÄ±ndaki 20 kare; el-kontrol.json doldurulacak.
- [x] HÄ±z: panoramada parÃ§a baÅŸÄ±na 5,1â€“5,5 kat neden (Ã¶nceki Ã¶lÃ§Ã¼m 3,3 kat)? Gerileme yok: dilim baÅŸÄ±na 7,1 ms aynÄ±, bu geometri 30 yerine 55 dilim/kare. docs/measurements/panorama-speed-attribution-2026-11-13.json
- [x] 3 dilim, 4 dilime karÅŸÄ± Ã¶n kayÄ±tlÄ± Ã¶lÃ§Ã¼ldÃ¼: KALDI (%96,3, ÅŸart %97); varsayÄ±lan deÄŸiÅŸmedi. docs/measurements/panorama-tiles-3-vs-4-result.json
- [x] ParÃ§a parÃ§a sonuÃ§: biten parÃ§a iÅŸ sÃ¼rerken DB'ye alÄ±nÄ±r, panel ilerlemeyi gÃ¶sterir; gerÃ§ek koÅŸuda ilk 5 dk 1623. sn'de gÃ¶rÃ¼ndÃ¼ (iÅŸ 2496 sn). docs/measurements/progressive-ingest-verification-2026-11-13.json
- [x] ParÃ§alÄ± birleÅŸtirmede yalnÄ±z ilk parÃ§anÄ±n paslarÄ± kalÄ±yordu; hepsi birleÅŸtirilir.
- [x] Paneldeki ilerleme satÄ±rÄ± gerÃ§ek iÅŸle tarayÄ±cÄ±da doÄŸrulandÄ± (iÅŸ 7bb3b379bb, maÃ§ 990808: "ilk 5 dk hazÄ±r Â· 1/3 parÃ§a").
- [x] Saha dÄ±ÅŸÄ± dilim pencerelerini atlama Ã¶n kayÄ±tlÄ± Ã¶lÃ§Ã¼ldÃ¼: KALDI. Ã‡Ä±ktÄ± birebir aynÄ± (16453/16453) ama 55 pencereden yalnÄ±z 8'i atÄ±ldÄ±, sÃ¼re %4 kÄ±saldÄ± (ÅŸart %15); kod geri alÄ±ndÄ±. docs/measurements/pitch-window-skip-result.json
- [x] ÃœrÃ¼n sÄ±navÄ± 4. deneme (sÃ¼re ÅŸartÄ± 6 kat, sonuÃ§ gÃ¶rÃ¼ldÃ¼kten sonra gevÅŸetildi): otomatik ÅŸartlar 8/8, oran 5,958; el kontrolÃ¼ bekliyor. (8223399, docs/measurements/product-full-match-exam-result-attempt4.json)
- [x] 4. denemenin 20 karelik kontrolÃ¼ (Claude yaptÄ±, insan deÄŸil): isabet 0,959, hayalet 0,028; iki ÅŸart tuttu. Ä°nceleme aracÄ± yarÄ±m saniye erken kare okuyordu, ffmpeg ile dÃ¼zeltildi. Bulgu: takÄ±m rengi sÄ±k sÄ±k yanlÄ±ÅŸ.
- [x] TakÄ±m rengi Ã¶lÃ§Ã¼ldÃ¼ (117093, 4. deneme Ã§Ä±ktÄ±sÄ±, 120 kare): renk kuralÄ±yla etiketlenebilen 1510 iÅŸaretin %78,3'Ã¼ doÄŸru takÄ±mda; parÃ§a baÅŸÄ±na %73â€“85, parÃ§alar arasÄ± takÄ±m yer deÄŸiÅŸtirmesi yok; iÅŸaretlerin %11'inde takÄ±m yok. AraÃ§ scripts/soccertrack_v2/team_color_spot_check.py, kayÄ±t docs/measurements/team-color-spot-check-117093-2026-11-13.json. Referans insan etiketi deÄŸil.
- [ ] TakÄ±m atamasÄ±nÄ± dÃ¼zelt. Engel: baÄŸÄ±msÄ±z etiketli gÃ¼ndÃ¼z verisi yok (HF token). Ã–nceki Ã¼Ã§ Ã¶n kayÄ±tlÄ± deneme (Ã§apa, kapÄ±lÄ± Ã§apa, iz iÃ§i oylama) kaldÄ±; sebep iz iÃ§i kimlik kaymasÄ± (docs/TAKIM-CAPA-DENEYI-SONUCLARI.md). Bitti sayÄ±lÄ±r: gÃ¶rÃ¼lmemiÅŸ etiketli veride Ã¶n kayÄ±tlÄ± ÅŸart geÃ§ince.
- [ ] Panoramada sÃ¼re ÅŸartÄ± hÃ¢lÃ¢ aÃ§Ä±k (kullanÄ±cÄ± kararÄ±): ÅŸartÄ± gevÅŸet, takip hÄ±zÄ±nÄ± dÃ¼ÅŸÃ¼r (Ã¶lÃ§Ã¼lmedi), ya da saha dÄ±ÅŸÄ± dilimleri atla (dedektÃ¶r dilimleme kodu dondurulmuÅŸ).
  Done when: sebep Ã¶lÃ§Ã¼mle gÃ¶sterildi; dÃ¼zeltme varsa Ã¶n kayÄ±tlÄ± yeni denemede sÃ¼re ÅŸartÄ± sÄ±nandÄ±.
- [x] Bellek kapÄ±sÄ± 1080p'den bÃ¼yÃ¼k karede 14 GB; iÅŸÃ§i tarafÄ±ndaki ret sebebiyle gÃ¶sterilir. (a63fe75)
- [ ] 132877 ve tam maÃ§: kullanÄ±cÄ±dan HF_TOKEN gerekli.
- [x] EskimiÅŸ README'ler (app/ai, app/agents, app/engine, app/api) gerÃ§ek durumu anlatsÄ±n. (855172c)
- [x] Panorama yÃ¼klemesinde 6 dilim GPU belleÄŸini taÅŸÄ±rÄ±yordu; dilim sayÄ±sÄ± kare baÅŸÄ±na 50 dilim sÄ±nÄ±rÄ±yla dÃ¼ÅŸÃ¼rÃ¼lÃ¼r. (db6508e)
- [x] El kontrol sayfasÄ± aracÄ±: scripts/urun_mac_el_kontrol.py (5a9c940)
- [x] KullanÄ±mdan kalkan utcnow / 422 sabiti temizlendi. (31eed5e)
- [x] Sabah raporu: docs/GECE-RAPORU-2026-11-13.md
- [x] MaÃ§ raporu ucu: `GET /tracking/matches/{id}/report` dilim dilim takÄ±m ÅŸekli + pres, gÃ¼venilir dilim Ã¶zeti, ortalamadan sapma bulgularÄ±, sÄ±nÄ±rlar yanÄ±tta. 4. deneme verisinde (990809, 5 dk dilim) 6/6 dilim gÃ¼venilir; yerleÅŸim desteÄŸi %3â€“9 Ã§Ä±ktÄ±ÄŸÄ± iÃ§in yerleÅŸim yazÄ±lmÄ±yor (eÅŸik %50). DoÄŸruluk Ã¶lÃ§Ã¼mÃ¼ deÄŸildir.
- [x] MaÃ§ raporu ekranÄ±: Video Analiz sayfasÄ±nda rapor kartÄ± (Ã¶zet, Ã¶ne Ã§Ä±kanlar, dilim tablosu, sÄ±nÄ±rlar; dilim 5/10/15 dk). 990809 verisiyle tarayÄ±cÄ±da doÄŸrulandÄ±.
- [x] (PR 380, c5ab236: operatÃ¶r 1. yarÄ± yÃ¶nÃ¼ + devre arasÄ±) MaÃ§ raporunda saha yÃ¶nÃ¼: hÃ¼cum yÃ¶nÃ¼ bilinmeden blok yÃ¼ksekliÄŸi ve geri hat verilemiyor; yÃ¶n kaynaÄŸÄ± (operatÃ¶r seÃ§imi ya da Ã¶lÃ§Ã¼lmÃ¼ÅŸ otomatik yÃ¶n) baÄŸlanÄ±nca eklenir.
- [x] MaÃ§ raporu bulgu eÅŸikleri gerÃ§ek konumda Ã¶lÃ§Ã¼ldÃ¼ (aÅŸaÄŸÄ±daki madde, match-report-vs-gt.json).
- [x] Fiziksel yÃ¼k (takÄ±m dÃ¼zeyi): maÃ§ raporunda oyuncu-dakika baÅŸÄ±na metre, yÃ¼ksek hÄ±z ve sprint payÄ±, kapsama ve gÃ¼venilirlik; ham hÄ±z yerine 1 sn dÃ¼zeltilmiÅŸ konum (ham hÄ±zda yÃ¼kleme yolunda oyuncu-zamanÄ±n %8,5'i sprint gÃ¶rÃ¼nÃ¼yordu). GeliÅŸtirme (canlÄ± yol, 132877 600-1200): 121,7 vs GT 121,1 m/dk.
- [ ] Fiziksel yÃ¼k gÃ¶rÃ¼lmemiÅŸ doÄŸrulama: 132877 1800-2100 yÃ¼kleme yolu koÅŸusu sonrasÄ± `physical_load_vs_gt` (Ã¶n kayÄ±t: docs/measurements/physical-load-vs-gt-132877-preregistration.json). Engel: bellek (14 GB boÅŸ commit).
- [x] MaÃ§ sonu raporu PDF'i: `GET /tracking/matches/{id}/report.pdf` (aynÄ± rapor, tek sayfa, Biz/Rakip `our_side`a gÃ¶re, Vera yazÄ± tipi ile TÃ¼rkÃ§e) ve maÃ§ raporu kartÄ±nda "PDF indir". GerÃ§ek gÃ¼ndÃ¼z Ã§Ä±ktÄ±sÄ±yla denendi: SoccerTrack 117093 ilk yarÄ± (iÅŸ 0b9979c312) geÃ§ici SQLite'a yÃ¼klendi, iki uÃ§ 200, PDF tek sayfa. SÄ±nÄ±r: arayÃ¼z dÃ¼ÄŸmesi canlÄ± modda tarayÄ±cÄ±da tÄ±klanarak denenmedi (tsc + eslint temiz); rapor yalnÄ±z takÄ±m dÃ¼zeyi, oyuncu bazÄ±nda deÄŸil.
- [x] KulÃ¼p pilot belgesi `docs/KULUP-PILOT.md`: sÃ¶z, kanÄ±tlÄ± sayÄ±lar (her biri Ã¶lÃ§Ã¼m dosyasÄ±na baÄŸlÄ±), yapÄ±lmayanlar, pilot Ã¶nerisi.
- [x] MaÃ§ raporu PDF baÅŸlÄ±ÄŸÄ±nda takÄ±m adlarÄ± ve maÃ§ tarihi; ad kayÄ±tlÄ± deÄŸilse "TakÄ±m {id}".
- [ ] KulÃ¼bÃ¼n kendi geniÅŸ aÃ§Ä±lÄ± maÃ§ videosuyla uÃ§tan uca koÅŸu + PDF'in analistle okunmasÄ± (video kullanÄ±cÄ±dan).
- [x] MaÃ§ raporu bulgu eÅŸikleri gerÃ§ek konuma karÅŸÄ± (betimleyici, gÃ¶rÃ¼lmÃ¼ÅŸ veri): `scripts/soccertrack_v2/eval_match_report.py`, `docs/measurements/match-report-vs-gt.json`. DakikalÄ±k dilimde bulgu kesinliÄŸi 132877 %57, 132831 %41; derinlik bulgularÄ± 22'de 6 doÄŸru â†’ rapordan Ã§Ä±karÄ±ldÄ± (sonra %72 / %58). AÃ§Ä±k: Ã¼rÃ¼ndeki 5 dk'lÄ±k dilimle tam maÃ§ta Ã¶lÃ§Ã¼m (GT'li tam maÃ§ yok).
- [x] Ä°ÅŸ durumu ucu yarÄ±ÅŸ anÄ±nda 500 veriyordu (`GET /tracking/jobs/{id}`): iÅŸ dosyasÄ± `open("w")` ile boÅŸaltÄ±lÄ±p yazÄ±lÄ±rken kilitsiz okunuyordu; CI'da iki kez dÃ¼ÅŸtÃ¼ (PR 372 ilk koÅŸu, main c0d548f). DÃ¼zeltme: yan dosyaya yazÄ±p `os.replace`, okuma ve listeleme aynÄ± kilitle. Regresyon testi eski kodda dÃ¼ÅŸÃ¼yor.
- [x] Ä°lk kurulumda (boÅŸ veritabanÄ±) `physical_tests` ve diÄŸer ayrÄ± modÃ¼l tablolarÄ± oluÅŸmuyordu: `dev_seed` yalnÄ±z `app.db.models`'i iÃ§e aktarÄ±p `create_all` Ã§aÄŸÄ±rÄ±yordu; ana sayfanÄ±n kadro listesi 500 veriyor, sayfa "backend baÄŸlÄ± deÄŸil" diyordu. DÃ¼zeltme: `MODEL_MODULES` + `load_models()`; test, tablo tanÄ±mlayan her `app/db` modÃ¼lÃ¼nÃ¼n listede olmasÄ±nÄ± ÅŸart koÅŸar. TarayÄ±cÄ±da doÄŸrulandÄ± (canlÄ± mod, 13 sayfa, arka uÃ§ta 500 yok; maÃ§ raporu PDF dÃ¼ÄŸmesi 200).
- [ ] `/admin` sayfasÄ±nda hydration uyumsuzluÄŸu: `RequireRole` sunucuda "GiriÅŸ gerekli.", istemcide "Yetki kontrol ediliyor..." basÄ±yor (React toparlÄ±yor, konsolda hata). Done when: ilk Ã§izim iki tarafta aynÄ±.
- [x] Video Analiz saha overlay'inde "~162 km/h" etiketi: top hÄ±zÄ±nÄ±n 45 m/s tavanÄ±na yapÄ±ÅŸmÄ±ÅŸ deÄŸeriydi (990809'da top Ã¶rneklerinin 174/4679'u; oyuncuda 12 m/s tavanÄ± 4207/163023 Ã¶rnek, karelerin 3118/7496'sÄ±nda "En hÄ±zlÄ± ~43 km/h"). Tavandaki deÄŸer Ã¶lÃ§Ã¼m deÄŸil kÄ±rpÄ±lmÄ±ÅŸ sÄ±Ã§rama; arayÃ¼z artÄ±k gÃ¶stermiyor (`lib/tracking-geometry.ts` fmtKmh/fastestPlayer).
- [x] Fiziksel yÃ¼kteki sprint/yÃ¼ksek hÄ±z payÄ± tavana yapÄ±ÅŸmÄ±ÅŸ hÄ±z Ã¶rneklerinden etkilenmiyor: `engine/tracking/physical_load.py` hattÄ±n `velocity_mps` alanÄ±nÄ± kullanmaz, hÄ±zÄ± 1 sn dÃ¼zeltilmiÅŸ konumlardan kendisi alÄ±r ve 12 m/sn Ã¼stÃ¼ adÄ±mlarÄ± atar (kod okumasÄ±yla; ayrÄ±ca Ã¶lÃ§Ã¼lmedi).
- [x] MaÃ§ raporuna saha yÃ¶nÃ¼ + savunma hattÄ±/blok: operatÃ¶r yÃ¶nÃ¼ (`home_attack`, `halftime_minute`) ya da kaleci/en derin oyuncu Ã§Ä±karÄ±mÄ±; rapor, PDF ve arayÃ¼z kartÄ±. GerÃ§ek konuma karÅŸÄ± 5 dk dilimde medyan 0,65/0,5 m, blok uyumu %100/%75 (Ã¶lÃ§Ã¼t Ã¶nceden yazÄ±lÄ± geÃ§ti). docs/measurements/match-report-def-line-vs-gt.json
- [x] Faz ayrÄ±mÄ± denendi, Ã¶lÃ§Ã¼t KALDI (savunurken geniÅŸlik 8,2 m vs tÃ¼m kareler 5,2 m); rapora eklenmedi, kod 4774cd0'da. docs/measurements/match-report-phase-vs-gt.json
- [x] GeÃ§iÅŸ anlarÄ± kapÄ±sÄ± KALDI: karelerden top kaybÄ± kesinliÄŸi %17,5 (ÅŸart %60); kurulmadÄ±. AynÄ± Ã¶lÃ§Ã¼m dosyasÄ±.
- [x] Sahiplik alanÄ± pencere Ã§oÄŸunluÄŸu (1,0 sn) Ã¶lÃ§Ã¼t KALDI: kayÄ±p kesinliÄŸi %34,9 (ÅŸart %60), duyarlÄ±lÄ±k %52,4; yÃ¶ntem elendi. docs/measurements/frame-possession-window-vs-gt.json. Sonraki aday sahiplik kaynaÄŸÄ± top-oyuncu temasÄ±ndan deÄŸil olay verisinden/gerÃ§ek kulÃ¼p videosundan gelmeli.
- [x] Rakip raporu: `perspective=scout` PDF'i ("Ä°zlenen / KarÅŸÄ±sÄ±ndaki", raporun sayÄ±larÄ±ndan "NasÄ±l oynuyor" notlarÄ±) + arayÃ¼zde "Rakip analizi" kutusu. Notlar yeni Ã¶lÃ§Ã¼m deÄŸil; Ã§ok maÃ§lÄ± rakip profili yok.
