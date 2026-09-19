# Karne: tanım seçiminin bedeli — 14 Eylül 2026

Karnenin "Elit antrenörle uyum (değişiklik)" boyutu, motorun ne zaman
değişiklik önerdiğini gerçek antrenörün ne zaman değiştirdiğiyle kıyaslar.
Motorun "değişiklik öneriyor" hâli iki türlü tanımlanabiliyor:

- **dar** — külliyata yazılmış birincil öneri `değişiklik` mi?
- **geniş** — panelde değişiklik sinyali yandı mı (şimdi / paket / elit pencere)?

İkisi de meşru. Sorun hangisinin raporlanacağının nasıl seçildiğiydi.

## Hata: en iyisini seçip sabit tabana karşı raporlamak

```python
best = sh_loose if (sh_loose.engine_f1 or 0) >= (sh_strict.engine_f1 or 0) else sh_strict
```

İki tanımın **ölçülmüş** F1'inden büyüğü alınıyor, taban çizgisi ise sabit
kalıyordu — saat kuralı motora bakmadığı için iki tanımda da aynı.

Bu, deponun başka yerde açıkça eleştirdiği çoklu-karşılaştırma tuzağı. Aynı
tuzak bu projede ölçülmüştü: altı sinyal × iki yön arasından en iyisi, ortada
hiçbir bilgi yokken bile rastgele tabanın **0,056 üstüne** çıkıyordu
(`docs/KARNE-GRUP-ICI-SINYAL.md`). İki aday daha az şişirir ama sıfır şişirmez.

İroni şurada: aynı fonksiyon **eşik** seçiminin bedelini zaten ödüyordu —
saat kuralının eşiği bir yarıda seçilip öteki yarıda ölçülüyor. Disiplin
vardı, bir katman yukarıda uygulanmamıştı.

## Düzeltme

`split_half_definition` eklendi (`app/engine/coach_benchmark/compute.py`).
Tanım **öteki yarıda** seçilir, **bu yarıda** ölçülür; iki kolun ortalaması
raporlanır. Üç koruma:

1. **Ortak tik kümesi şartı.** Tanımlar aynı tikleri ve aynı hedefleri
   paylaşmıyorsa taban çizgisi tanımdan tanıma kayar ve kıyas anlamını yitirir.
   Bu durumda hüküm verilmez, "yetersiz veri" denir.
2. **Kararsızlık raporlanır.** İki yarı farklı tanım seçerse not'a
   `İKİ YARI FARKLI TANIM SEÇTİ` yazılır. Aynı kural yük sinyalleri için de
   ön-kayıtlı (`docs/MAC-ICI-YUK-PLANI.md`, kabul ölçütü 3).
3. **Örneklem içi ayrı tutulur.** `in_sample` alanı yalnız gösterim içindir;
   hüküm oradan verilmez. Örneklem içi en iyi ile örneklem dışı arasındaki
   fark seçim bedelinin kendisidir ve not'a yazılır.

Ayrıntılı çıktı iki tanımı da ayrı ayrı basmaya devam ediyor — kaybolan bilgi
yok, yalnız **manşet sayı** artık bedeli ödenmiş olan.

## Sayı ne kadar değişir

Bilinmiyor; bu ölçüm külliyat ve maç dosyaları gerektiriyor ve burada yeniden
çalıştırılmadı. Değişimin yönü ise belli: örneklem dışı seçim, örneklem içi
maksimumdan **büyük olamaz**. Yani manşet F1 aynı kalır ya da düşer, yükselmez.

Boyutun hükmü (`taban çizgisiyle aynı` / `geçiyor` / `altında`) ±0,05 bandına
göre verildiği için, düşüş 0,05'i aşmadıkça hüküm de değişmez.

## Test

`tests/test_coach_benchmark.py` dört durumu sabitliyor:

- gerçekten iyi tanım iki yarıda da seçiliyor, `stable=True`;
- iki gürültü tanımıyla örneklem içi en iyi, örneklem dışından **yüksek**
  çıkıyor (bedel görünür) ve iki yarı farklı tanım seçiyor;
- farklı tik kümeleri reddediliyor;
- tek tanımda seçim yok, sonuç `split_half_agreement` ile birebir aynı.

## Nereden çıktı

Kod denetiminin tarama fazından. Dört ayrı tarayıcıdan üçü bağımsız olarak
`scripts/coach_iq.py:511`'i işaretledi. Doğrulama fazı oturum limitine takıldığı
için bulgular elle sınandı.
