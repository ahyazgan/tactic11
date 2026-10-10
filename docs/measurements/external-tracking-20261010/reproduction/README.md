# Araştırma sürücülerini tekrar çalıştırma

Bu dizindeki `.py.txt` dosyaları deney sürücülerinin metin kopyalarıdır; uygulama veya otomatik CI başlangıç noktası değildir. Model/maç dosyaları ve dış projelerin kodları pakete dahil değildir. Sonuçlar bu makinede Windows, Python 3.12.10, RTX 5060 Laptop GPU üzerinde alındı. Paket sürümleri `../runtime-versions.json` içindedir.

1. `.py.txt` kopyalarını repo kökündeki `.cache/external-study-20261010/` dizinine `.py` uzantısıyla yerleştirin. `../repositories-input.json` dosyasını aynı yerde `repos.json` adıyla kullanın. Sürücülerin göreli dizin yapısı bu konumu bekler.
2. Kaynaklar `acquire_sources.py` ile sabit commitlerden alınır. Model erişimi `model_access.py`, dört modelin indirilmesi `download_models.py` ile yapılır. Resmi JNR ViT-Small bağlantısı `../model-downloads.json` içindedir; `gdown` ile `models/uncertainty_vit_small.pth` adına indirilmiştir. SAM3 bu deneyin çalışır model girdisi değildir.
3. Ek paketleri `venv-cv` içine kurmak yerine `pip install --target .cache/external-study-20261010/site --no-deps --no-cache-dir` ile araştırma dizinine kurun. Tam ad/sürümler `../runtime-versions.json` içindeki `additional_packages` listesindedir. `cython-bbox` bu Windows ortamında derlenemedi; kullanılan NumPy uyarlaması `compat.py` içindedir. SAM2'nin opsiyonel CUDA delik doldurma eklentisi kurulmadı; özgün kodun desteklediği geri dönüş yolu kullanıldı.
4. Mevcut iki ham tespit cache'i, kaynak videoları, takım/kişi etiketleri, sabit renk referansları ve önceki GTA ReID ağırlığı gerekir. Kesin girdiler sürücüler ve `../trial-records.json` içindeki manifestlerde belirtilir. Kaynak videoları değiştirmeyin. Yeni bağımsız kontrol kliplerini bu deneylere eklemeyin.

Repo kökünden, **GPU/model deneylerini sırayla**, örneğin:

```powershell
venv-cv\Scripts\python.exe .cache/external-study-20261010/check_evidence.py
venv-cv\Scripts\python.exe .cache/external-study-20261010/prepare_crops.py
venv-cv\Scripts\python.exe .cache/external-study-20261010/run_jersey.py
venv-cv\Scripts\python.exe .cache/external-study-20261010/run_calibration.py
venv-cv\Scripts\python.exe .cache/external-study-20261010/run_smp.py --group day --segment 3 --name smp_day3_reproduction
venv-cv\Scripts\python.exe .cache/external-study-20261010/run_smp.py --group night_old_control --segment 40 --name smp_night40_reproduction
venv-cv\Scripts\python.exe .cache/external-study-20261010/run_mcbyte.py --group day --segment 3 --name mcbyte_day3_nomask_reproduction --no-mask
venv-cv\Scripts\python.exe .cache/external-study-20261010/run_mcbyte.py --group night_old_control --segment 40 --name mcbyte_night40_nomask_reproduction --no-mask
venv-cv\Scripts\python.exe .cache/external-study-20261010/score_runs.py
```

Birleşim deneyi `blend_identity.py` içindedir. Bu sürücü özgün `mcbyte_day3_nomask_v1` ve `mcbyte_night40_nomask_v1` tahmin dizinlerini bekler. Yeni isimlerle tekrar üretirken sürücünün bu iki girişini kendi deneme adlarınızla eşleştirin; ardından `blend_identity.py` ve `score_runs.py` çalıştırın. Birleşim varsayılan uygulama takibini değiştirmez. Gözlem/takım eşitliğini ve tek karede kimlik çakışmamasını kontrol eder. İki klip, adayın oluşturulmasında zaten görüldüğü için bağımsız doğrulama sayılmaz.

Her `--name` yeni olmalıdır; tamamlanmış sonuç dizinine yazma reddedilir. JNR/kalibrasyon özet dosyaları sabit isimlidir; önceki bir çalışmayı korumak için kopyasını alın. Model ve veri erişimi, donanım ve bağımlılıkların hazır olmasına bağlıdır; komut listesinin bulunması bütün ortamlar için kurulum garantisi değildir.

`--no-mask`, McByte++'ın maske bileşenini kapatan bir **bileşen çıkarma deneyi**dir. Tam McByte++ sonucu olarak sunulmamalıdır. Tam maske sürümü beş karelik çalıştırma testinden geçti; uzun tam çözünürlüklü deneme tamamlanmadı. Kodda ReID başlangıcı zorunlu kontrol edilir. Bozuk/kısmi yüklemeyle sessizce devam edilmez.

SMP deneyinde dış projenin `benchmark` birleştirme yolu kullanıldı. Buna rağmen kaynak dedektör kutularına karşılık gelmeyen maske kutuları çıktı. Son sürücü bunları `invalid_source_boxes_excluded` olarak kaydeder, tespit puanına katmaz ve herhangi bir böyle çıktı varsa terfiyi engeller. Geriye kalan gerçek kutular puanlanır. Bu, özgün projenin ilan ettiği benchmark skorunun yeniden üretimi değildir.

Eşleşme maliyetini kaydetme, Windows video yükleme/CPU aktarımı ve IoU uyumluluğu açık uyarlamalardır. Kaynak kutuları ve renk geçmişi için ByteTrack tekrar üretiminin birebir eşitliği kontrol edilir. Skor dosyası yalnızca iki uç noktası aynı seçilmiş klipte bulunan ilişkileri puanlar. Belirsiz kişi etiketleri dışarıda tutulur. Farklı etiket dosyalarındaki ilişkiler birbirini tekrar edebildiği için sonuçları toplayıp benzersiz toplam kişi doğruluğu diye sunmayın.

Bu araştırma, 15 projenin hepsinin uçtan uca çalıştırıldığı iddiasını içermez. Hangi projenin yalnızca kodunun incelendiği, hangisinin modelinin çalıştığı ana raporda tek tek belirtilmiştir.
