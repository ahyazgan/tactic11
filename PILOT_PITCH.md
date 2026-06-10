# manager2 — Pilot Programı (Detaylı Pitch)

**Süper Lig kulübü teknik direktör, analiz şefi, sportif direktör** için
veri-tabanlı karar destek platformu. Tek-cümle: AI co-pilot + kalibre
edilmiş tahmin motoru + 11 specialized agent.

## Sayılar (bugün)

| Metrik | Değer |
|---|---|
| Otomatik test | **1,432 yeşil** (CI'da %100 pass rate) |
| Engine modülü | **16** (form, rating, opponent, predict, xG, load, tracking, calibration, schedule, matchup, fixture_difficulty, predict_ml, player_form, set_piece, player_similarity, formation_matcher) |
| Agent (AI brief üretici) | **11** (PreMatch, PostMatch, MegaMatch, OpponentScout, InjuryLoad, Lineup, Substitution, Tactical, Weekly, ScoutWatchlist, MediaBrief) |
| Tahmin modeli | Dixon-Coles + ML-kalibre ρ + logistic xG |
| Multi-tenant | ✅ tenant_id 16 tabloda + JWT + RBAC |
| Adapter | API-Football, StatsBomb Open, FixtureTracking |
| Migration | 13 alembic versiyonu, rolling deploy uyumlu |

## 4 ana ürün modülü

### 1. **Yardımcı Manager (AI co-pilot)**
> "Cuma Fener maçına nasıl çıkalım?"

Claude tool-use ile DB'den **gerçek veriyle** cevap üretir. 10 tool:
form, rating, predict, h2h, schedule, player_load, ML status, roster proxy.
Çok-turlu konuşma kalıcı (chat_conversations tablosu). Takıma özel hafıza
(`assistant_memory`) — "geçen ay bu rakibe yüksek pres denedin, sonuç…".

### 2. **Decision Brief Otomasyonu**
Her sabah **09:00**'da `daily_decision_brief` job:
- Tüm aktif tenant'lar için bu haftaki maçları bulur
- Her maç için: lineup öneri + pre-match brief + mega brief üretir
- HMAC-SHA256 imzalı webhook'la analiz şefine gönderir (Slack/email)

### 3. **Kalibre Tahmin Motoru**
- **Dixon-Coles** baz model (Poisson + ρ düzeltmesi, literatür standardı)
- **engine.predict_ml**: ρ her gece geçmiş tahminlerden grid-search ile öğrenilir
- **xG**: trained logistic regression (StatsBomb Open ile) ya da geometric fallback
- Kalibrasyon ölçümü: `/admin/predict-accuracy` Brier + log loss + ECE

### 4. **Scout aracı**
- Watchlist + Z-score alert ("3 hafta üst üste yüksek dakika → scout gönder")
- **Player similarity**: cosine similarity per-90 vektörden, "X oyuncuya benzer 10 oyuncu"
- Manager performance dashboard: xPts vs actual → "TD performansını veriyle ölç"

## Demo — pilot kulübe gösterilecekler

### Tek komut canlı demo (~7 saniye)
```bash
python scripts/pilot_demo.py --reset
```
Çıktı: login JWT → Süper Lig sync → agent zinciri (Lineup + PreMatch + MegaMatch)
→ Dixon-Coles tahmin → asistan chat → "PILOTA GÖSTERILECEK" özet.

### Slide için markdown export
```bash
python scripts/pilot_demo.py --output md > slides/demo.md
```

## Pilot fiyatlandırma (görüşmeye açık)

### Standart — $8,000 setup + $1,500/ay (6 ay)
- Tek tenant kurulum (kulübün kendi VPS'inde)
- API-Football Pro tier dahil
- Anthropic Claude API ile sınırsız AI brief
- Haftalık 1 saat görüşme
- 24 saat e-posta SLA
- 11 agent + yardımcı manager chat
- Dashboard (HTML — minimal; geliştirilebilir)

### Pro — $20,000 setup + $4,000/ay (6 ay)
- Standart + aşağıdakiler:
- **Custom engine modülleri** (örn. rotasyon planlayıcı, opponent prep brief)
- **Beyaz-etiket dashboard** (kulüp logo + renk paleti)
- **Vendor tracking entegrasyonu** (SecondSpectrum/Hawk-Eye — kulübün lisansı üzerinden)
- **xG model retrain ayda 1** (yeni veriyle)
- 4 saat e-posta + 1 saat Slack SLA
- Aylık metrik raporu (Brier trend, agent kullanım, ROI)

### Enterprise — özel teklif
- Multi-tenant SaaS — birden çok kulüp tek deploy'da
- Mobil uygulama (React Native)
- Tam React/Next.js frontend (FM 2010-2015 estetik, 3 hafta dev)
- 24/7 destek

## Pilot kapsamı dışı (out-of-scope)

- Canlı maç içi xG (live event feed)
- Bahis odds engine (regulatif risk)
- Transfermarkt resmi entegrasyon (kulüp kendi lisansını sağlar)

## Pilot başvuru süreci

1. **0. hafta** — discovery: 1 saatlik görüşme, kulübün ihtiyacı + mevcut araçlar
2. **1. hafta** — setup: VPS + DB + API key'ler + 1. tenant + ilk sync
3. **2. hafta** — eğitim: 2 saatlik onboarding (TD, analiz şefi, scout)
4. **3-24. hafta** — operasyon: haftalık 1 saat check-in, ihtiyaca göre custom

## Pilot başarı kriterleri (KPI)

| KPI | Hedef (6 ay sonu) |
|---|---|
| Brier score (3-class) | < 0.55 (lig ortalamasından iyi) |
| Haftalık active user | ≥ 3 (TD + scout + analiz şefi) |
| Agent çıktısı / hafta | ≥ 20 brief üretildi |
| Scout watchlist boyutu | ≥ 30 oyuncu |
| Müşteri NPS | ≥ 8 |

## Teknik altyapı

- **Backend**: FastAPI + SQLAlchemy + Postgres
- **AI**: Anthropic Claude (Opus 4.7 ya da Sonnet 4.5 — pilot tercihi)
- **ML**: scikit-learn (LogisticRegression xG), pure-Python pure engine
- **Auth**: JWT + bcrypt + 4 rol (admin/analyst/coach/viewer)
- **Deploy**: Docker Compose tek komut, Hetzner Cloud €4.51/ay yeterli
- **Test**: 1,432 otomatik test, GitHub Actions CI
- **Lisans**: Codebase pilot kulübe license; Anthropic + StatsBomb kendi ToS

## İletişim

a.hakan_@hotmail.com — pilot görüşmesi için 30 dakika ayırın.

---

*Bu doküman canlı taslaktır. Fiyatlandırma, scope, KPI'lar müzakereye açıktır.*
