# manager2 — Süper Lig Pilot Programı

**Kim için:** Süper Lig kulüpleri (teknik direktör + analist ekibi), bahis/fantasy
operatörleri, spor medya yayın kuruluşları.

**Tek cümle:** Maç öncesi 200 kelimelik veri-kalibre brief + kalibrasyonu
kanıtlı 1X2 olasılığı + rakip analiz dashboard'u — kendi sunucunuzda, kendi
verilerinizle.

---

## Neyi teslim ediyoruz (bugün hazır)

### Tahmin motoru
- **Poisson + Dixon-Coles** olasılık modeli, literatür standardı (1997).
- **ML-kalibre ρ**: geçmiş tahminlerinizden grid-search ile en iyi `ρ` öğrenir;
  her gece yeniden train olur.
- **Kalibrasyon ölçümü**: Brier score, log loss, ECE (expected calibration error)
  → "tahminlerimiz iyi mi" sorusu sayıyla cevaplanır, his ile değil.

### Analiz katmanı
11 saf hesap modülü:
- form, rating (ev/dep ayrımı, time decay), opponent (H2H trendler),
  matchup, predict, schedule, fixture_difficulty (side-aware),
  load (oyuncu yükü), tracking (top-zone dağılımı), calibration.

### AI brief üretici
- Claude (Anthropic) ile **maç öncesi 200 kelimelik özet**: forma, kondisyon,
  rakip avantajı, kritik faktörler. Veri-anchored — uydurma sayı yok.
- Idempotent storage: aynı maç için yeniden çağrı = upsert.

### Operasyon
- Production hardening: rate limit, X-Request-ID propagation, JSON loglar,
  X-API-Key auth, secrets fail-fast, `/admin/quota-status`.
- Günlük backup script + restore drill rehberi.
- 4 paralel CI job (lint/test/migration/docker_build).
- Docker Compose ile **tek komut deploy**: `docker compose up -d`.

### Veri kaynakları
- **api-football** entegrasyonu (Süper Lig + Premier League + 1100+ lig).
- **Tracking adapter** (FixtureTrackingSource) — vendor swap için hazır;
  SecondSpectrum/Hawk-Eye gelince adapter eklenip pipeline değişmez.

### Sayılar
- **295+ otomatik test**, hepsi yeşil.
- 11 engine modülü, 30+ HTTP endpoint, 7 DB migrasyon.
- ~30K satır iyi-mimarli Python kod.

---

## 6 aylık pilot — ne sunuyoruz

| Madde | Standart | Pro |
|---|---|---|
| Kurulum (VPS veya kendi cloud'unuz) | ✓ | ✓ |
| Süper Lig sync + günlük ingest | ✓ | ✓ |
| `/admin/predict-accuracy` ile haftalık rapor | ✓ | ✓ |
| Maç başı 5 maç için AI brief üretimi | ✓ | ✓ |
| `/admin/ml-model-status` dashboard | ✓ | ✓ |
| Tracking adapter (sentetik fixture) | ✓ | ✓ |
| **Custom engine modülü** (rotasyon, opponent prep) | — | ✓ |
| **Vendor tracking entegrasyonu** (SecondSpectrum/Hawk-Eye) | — | ✓ |
| **Beyaz-etiket dashboard** (kulüp logo+renk) | — | ✓ |
| Haftalık 1 saat görüşme | ✓ | ✓ |
| 24 saat e-posta SLA | ✓ | ✓ |
| 4 saat e-posta + 1 saat Slack SLA | — | ✓ |

**Pilot fiyatlandırma** (örneklenebilir, görüşmeye açık):
- **Standart**: $8,000 setup + $1,500/ay
- **Pro**: $20,000 setup + $4,000/ay (vendor tracking entegrasyon dahil)

6 ay sonunda: kalibrasyon raporlarına göre değer kararı; devam etmek isterseniz
yıllık lisans + maintenance modeline geçiş.

---

## Pilot dışı (out-of-scope)

- Canlı maç içi olasılık güncellemeleri (xG anlık) — Faz K.
- Mobil app — Faz L (REST API hazır; mobil viewer ayrı RFC).
- Bahis kotalı dakika-dakika oran fiyatlama — bu pazar regulatif; ürünümüzün
  öncelikli yönü kulüp/medya tarafı.

---

## Riskler ve açık konular

- **API-Football kotanız**: Süper Lig + 1 başka lig için Pro tier (7500 req/gün)
  yeterli; daha geniş kapsam Pro tier üstüne çıkar.
- **Tracking verisi**: vendor entegrasyonu için kulübünüzün ya da liganın
  mevcut sözleşmesi gerekir; bağımsız tracking lisans satmıyoruz.
- **GDPR/KVKK**: Oyuncu performans verisi → ABD/EU veri sınırı kontrolü için
  kendi cloud'unuzda kurulum öneriyoruz; biz SaaS olarak host etmiyoruz.

---

## İlk demo için: 30 dakika

1. `git clone <repo>` + `cp .env.example .env` + `docker compose up -d`
2. `python scripts/demo.py` — Süper Lig sentetik veriyle uçtan-uca çıktı
3. `python scripts/api_football_smoke.py --key X --league 203 --season 2024`
   — anahtarınız çalışıyor mu doğrulaması
4. `curl http://localhost:8000/dashboard` — minimal web dashboard
5. Sorular + sonraki adım planlaması.

İletişim: a.hakan_@hotmail.com

---

*Bu doküman canlı taslaktır. Pilot şartları, fiyatlandırma, modül kapsamı
müzakereye açıktır.*
