# Top tespiti: olaylara karşı ölçüm, teşhis ve aday izi (2026-11-01)

Soru: panoramada sistemin "top" dediği şey gerçekten top mu, ve topu kimin
sürdüğünü (telestrasyonda savunan takım) ne kadar doğru biliyoruz?

## 1. Ölçüm: dokunuş olayları top GT'si yerine

SoccerTrack v2 panoramasında top etiketi yok. Ama `117092_player_nodes.csv` her
topa dokunuşta dokunan oyuncunun saha konumunu veriyor (ilk yarı 1225 dokunuş).
Dokunuş anında top o oyuncunun ayağındadır.

Eşleme GSR oyuncularına karşı bulundu (`scripts/soccertrack_v2/evaluate_ball_events.py`):

- x/y eksenleri yer değiştirmiş ve takıma göre normalize: 30798 iki eksende
  ters, 9834 düz (her takım kendi hücum yönüne göre yazılmış).
- Zaman: GSR karesi = olay_ms·25/1000 + 3; video saniyesi = olay − 0,28.
- Bu eşlemeyle dokunuş konumu en yakın GSR oyuncusuna medyan 1,0 m, %85'i ≤ 2 m.
- Olay takımı → GSR takımı konumla: 30798 → sağ (1), 9834 → sol (0) (%88 çoğunluk).

Ölçütler:

- **dokunuş**: olay anına en yakın karede top ≤ R m → isabet; uzak → yanlış; yok → kayıp.
- **uçuş**: başarılı kısa pasın zaman ortasında top, pasör–alıcı doğru parçasına ≤ R m.
  Topu hep bir oyuncunun ayağına koyan yöntem burada kaybeder.
- **savunan takım** (`eval_telestration --possession-events`): telestrasyonun çizdiği
  karelerde savunan takım, aynı takımın ardışık iki dokunuşu arasındaki (≤ 4 sn)
  sahipliğin tersi mi. Koça giden asıl çıktı bu.

Sınır: takip konumlarının kendisi GSR'ye karşı medyan ~2,4–3 m sapıyor (kalibrasyon +
hayalet tespitler); bu yüzden ana yarıçap 5 m, 3 m ikincil.

## 2. Teşhis: "top"un çoğu saha dışındaki sabit bir nesne

v2 ile üretim takibi (600–960 sn, 1080p koşu 990611):

| | Değer |
|---|---|
| Top bulunan kare | %92,4 |
| Bunların tek bir noktadaki payı (saha x≈58, y≈97) | %78 |
| Dokunuşta top ≤ 5 m | %8,8 |
| Dokunuşta top yanlış yerde | %87,5 (medyan hata 43 m) |
| Çizilen karelerde savunan takım doğru | %78,5 |

Tek nokta, saha sınırının ~310 px dışındaki parlak bir nesne (gece maçı; daha önceki
tanı gündüz kaydında hiç görmemişti, `docs/TOP-SINIR-UYUSMAZLIGI-TANI.md`). Takip her
karede en güvenli adayı seçiyor; hattın saha kontrolü yalnız metreye bakıyor ve TPS
dış kestirimi nesneyi saha içine taşıyor. Dondurulmuş takip koduna dokunulmadı.

Dokunuş anlarında (geliştirme, 80 dokunuş) tam kare dedektör adayları:

| | Ham | Saha dışı karartılmış |
|---|---|---|
| Topa ≤ 5 m aday (güven ≥ 0,1) | %40 | %39 |
| Topa ≤ 5 m aday (güven ≥ 0,4) | %15 | %17 |
| En güvenli aday topa ≤ 5 m | %12 | %17 |

Sahte nesneyi atmak yanlışları siliyor ama dokunuşta isabeti artırmıyor: ayak
dibindeki gerçek top çoğunlukla düşük güvenle bulunuyor ve üretim eşiği (0,3) onu
eliyor. Asıl kaldıraç düşük güvenli adaylar + zaman tutarlılığı.

## 3. Aday kaydı: takip aynı, düşük güvenli toplar yan dosyada

`scripts/track_live_candidates.py` dondurulmuş `track_live`'ı sarar: dedektör 0,1
eşikle kurulur ama hatta yine üretim eşiğinin (0,3) üstü verilir; her örneklenen
karedeki bütün top adayları `<watch>/ball_candidates/<segment>.json` dosyasına yazılır.
Ek GPU işi yoktur.

Doğrulama (aynı segment, iki koşu): 375 karenin hepsinde top ve oyuncular birebir
aynı, top kaynak sayıları aynı (det 217 / roi 35 / interp 86). Karede ortalama 12,8
aday kaydedildi; bunların %23'ü 0,3'ün üstünde.

Adayların çoğu sabit: aynı pikselde segment boyunca duran ışık, çizgi kesişimi gibi
nesneler (bir segmentte 36 hücre). Bunlar ayıklanınca karede ortalama 2,6 aday kalıyor.
Kalanların bir kısmı oyuncu ayakkabısı/çorabı; topu süren oyuncunun ayağındaki gerçek
toptan ayırmak asıl zorluk.
