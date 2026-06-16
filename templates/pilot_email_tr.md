# Pilot e-posta şablonları (Türkçe)

## Şablon 1 — İlk soğuk e-posta (TD / Sportif Direktör)

**Konu:** `{kulüp_adı}` için veriyle karar destek — 30 dk demo

```
Sayın {ad_soyad},

Süper Lig'de teknik kararların veri ile desteklenmesi giderek standart hale
geliyor. Sportradar gibi büyük sağlayıcılar lig-bazlı sözleşmeler yaparken,
kulüp-bazlı ve kendi verisi üstünde çalışan bir araç çoğu kulüpte eksik.

Biz {kulüp_adı} için tasarlanmış bir AI co-pilot geliştirdik:

- Maç günü öncesi otomatik brief: 11'in önerisi, rakip zayıflık analizi,
  yorgun oyuncu uyarısı (her sabah 09:00'da e-postanızda)
- Yardımcı manager chat: "Cuma {rakip_adı} maçına nasıl çıkalım?" diye
  sorduğunuzda, kulübün veri ambarından çekip 100-150 kelimelik gerekçeli
  cevap alırsınız
- Tahmin doğruluğu izleme: model haftalık kalibre edilir, "biz iyiyiz" demek
  yerine Brier score ile gösteririz
- Scout aracı: izlediğiniz oyuncuların per-90 metrikleri otomatik takip,
  benzer profilde alternatif öneri

Pilot 6 ay, ilk ay ücretsiz deneme. Mevcut araçlarınızla yan yana,
operasyonunuzu bozmadan kurarız.

30 dakikalık demo'da gerçek Süper Lig fixture verisi üzerinde size canlı
gösterebilirim. {önerilen_tarih_1} veya {önerilen_tarih_2} uygun mu?

Selamlar,
{senin_adın}
{telefon} | {email}
```

## Şablon 2 — Sportif direktöre takip (1 hafta sonra)

**Konu:** Hatırlatma — {kulüp_adı} pilot demo

```
Sayın {ad_soyad},

Geçen hafta yazdığım e-posta için dönüş alamadım; muhtemelen yoğun
geçiyordur diye düşündüm.

Sadece kısa bir hatırlatma: 30 dakikalık demo ile {kulüp_adı}'a özel ne
yapabileceğimizi göstermek için ekibimden somut bir şey hazırladım.

Pilot için sıfır risk vaadiniz var:
- İlk ay ücretsiz
- Sözleşmeyi 30 gün önceden uyararak istediğiniz zaman iptal edebilirsiniz
- Verileriniz sizin VPS'inizde, biz host etmiyoruz (GDPR/KVKK uyumlu)

Bu hafta uygun olduğunuz yarım saati paylaşır mısınız? Calendly linki:
{calendly_link}

İyi haftalar,
{senin_adın}
```

## Şablon 3 — Analiz şefine teknik takdim

**Konu:** {kulüp_adı} analiz ekibine veri platformu

```
Sayın {ad_soyad},

{ortak_tanıdık_varsa: "{ortak_tanıdık} sizden bahsetti, "}
{kulüp_adı}'nın analiz ekibinde çalıştığınızı biliyorum. Geçen sezon
{kulüp_adı}'nın {örnek_başarı/zorluk} dikkatimi çekmişti.

tactic11 — Süper Lig odaklı bir veri platformu. Mevcut Wyscout/StatsBomb
abonelerinin üstüne kurulan bir analiz katmanı, kendi başına bir veri
sağlayıcı değil. Saf hesap mimarisi (engine layer DB/HTTP'ye dokunmaz)
sayesinde sizin mevcut araçlarınızla yan yana çalışır.

Analiz şefi için kritik özellikler:

1. **Tahmin kalibrasyonu**: model çıktısı her hafta `Brier score + ECE` ile
   ölçülür. "Biz iyiyiz" yerine "son 30 günde 0.48 Brier, lig ortalamasından
   %15 iyi" gibi somut çıktı.

2. **Audit trail**: her engine sonucu yanında `AuditRecord` (formula, inputs,
   subject_id). "Bu öneri nereden geldi?" sorusu daima açık.

3. **Asistan chat**: ekibinizin günlük "X oyuncu Y'a benzer mi" sorularına
   doğal dilde cevap. 10 read-only tool ile DB'den okur, uydurmaz.

4. **xG modeli**: kendi shot verinizle retrain edebilirsiniz; literatür
   katsayıları (Caley 2014) ile fallback.

Bir saat boyunca codebase'i + dashboard'u sizinle paylaşabilirim. GitHub
read access verebilirim (private repo). Uygun olduğunuz zaman söyleyin.

Selamlar,
{senin_adın}
```

## Şablon 4 — Pilot sözleşmesi sonrası onboarding

**Konu:** Hoş geldiniz — pilot kurulum + ilk hafta

```
Merhaba {ekip_adı},

Pilot sözleşmesi imzalandı, hoş geldiniz! İlk hafta planı:

**Bugün (gün 0)**
- VPS sağlandı: {vps_ip}
- {kulüp_adı} tenant oluşturuldu
- Admin kullanıcı: {admin_email}
- Dashboard: https://{kulüp_domain}/dashboard

**1. gün — kurulum (1 saat, online)**
- API-Football anahtarınızla bağlantı testi
- İlk Süper Lig + UEFA sezon sync (yaklaşık 200 maç ingest)
- Kalibrasyon raporu için ilk 10 maç tahmini

**2-4. günler — eğitim (3 × 30 dk)**
- TD: yardımcı manager chat + decision brief
- Scout şefi: watchlist + similarity
- Analiz şefi: calibration metrik panosu

**5. gün — değerlendirme**
- "Şu ana kadar ne çalıştı, ne eksik" 30 dk

İlk haftada her gün e-posta + Slack desteği. Sorun bildirim:
{support_email} ya da Slack #tactic11-pilot kanalı.

Hoş geldiniz!
{senin_adın}
```

## Şablon 5 — Aylık raporlama

**Konu:** {kulüp_adı} aylık tactic11 raporu — {ay_adı}

```
Merhaba,

{ay_adı} ayının tactic11 raporu hazır.

**Kullanım:**
- Maç önü brief üretimi: {brief_count} (önceki ay {önceki_brief_count})
- Aktif analiz şefi: {active_user_count} kişi
- Asistan chat: {chat_message_count} mesaj
- Scout watchlist: {watchlist_size} oyuncu

**Tahmin kalibrasyonu (son 30 gün):**
- Brier score: {brier_score} ({brier_trend})
- Log loss: {log_loss}
- ECE: {ece}
- Reconcile edilmiş tahmin: {reconciled_count}

**xG modeli:**
- Versiyon: {xg_model_version}
- Son train: {xg_trained_at}
- ROC-AUC: {xg_roc_auc}

**Aksiyon öğeleri:**
{action_items_bullet_list}

**Sonraki ay öncelikleri:**
{next_month_priorities}

Sorularınız için her zaman ulaşabilirsiniz.

{senin_adın}
```

## Şablon 6 — Pilot sonu yıllık geçiş

**Konu:** {kulüp_adı} pilot 6 ayı tamamlandı — yıllık lisans

```
Sayın {ad_soyad},

6 aylık pilot tamamlandı. Özetle:

**Veri:**
- {brief_count_total} maç önü brief üretildi
- Brier score pilot başında {start_brier} → bugün {end_brier} ({trend_pct} iyileşme)
- {kullanıcı_kullanım_anekdot}

**Geri bildirim:**
- {kullanıcı_alıntı_pozitif}
- {iyileştirme_isteği}

**Önerilen yıllık geçiş:**
- Yıllık fiyat: ${annual_price} (pilot fiyatından %{discount_pct} indirim)
- Aynı SLA + 2 yeni özellik: {feature_1}, {feature_2}
- 3 yıl rolling sözleşme opsiyonu (%{multi_year_discount} ek indirim)

Sözleşme metni ekte. Sorularınız varsa görüşmeye hazırım.

İyi bayramlar / iyi seneler / iyi sezonlar,
{senin_adın}
```

---

## Notlar

- Tüm şablonlar `{placeholder}` formatında — gönderim öncesi kulübe özelleştir
- Türkçe + saygılı dil; "siz" formal
- Cold e-mail başarı oranı %5-10 — 20 kulübe yaz, 1-2 cevap bekle
- Calendly + custom landing page olursa daha iyi
- LinkedIn DM Cold mail'den 3x daha iyi convert eder (Süper Lig analitik
  topluluğu küçük)
