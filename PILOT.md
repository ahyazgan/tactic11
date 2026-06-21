# tactic11 — Süper Lig Pilot Programı

> **Bu doküman arşivlendi.** Güncel ve tek-kaynak pilot pitch'i:
> **[`PILOT_PITCH.md`](./PILOT_PITCH.md)**
>
> Eski sürümdeki rakamlar (295 test / 11 engine) güncelliğini yitirmişti.
> Doğrulanmış güncel rakamlar (2.078 test / 121 engine / 15 agent) için
> `PILOT_PITCH.md`'ye bakın. İki dokümanı senkronda tutmak yerine tek kaynak
> bırakıyoruz — çelişen sayı = kaybolan güven.

---

## Hızlı özet (tek cümle)

Maç öncesi 200 kelimelik veri-kalibre brief + kalibrasyonu kanıtlı 1X2
olasılığı + rakip analiz dashboard'u — kendi sunucunuzda, kendi verilerinizle.

## İlk demo için: 30 dakika

1. `git clone <repo>` + `cp .env.example .env` + `docker compose up -d`
2. `python scripts/pilot_demo.py --reset` — Süper Lig verisiyle uçtan-uca çıktı
3. `python scripts/calibration_report.py` — Brier/log-loss/ECE kalibrasyon kanıtı
4. `curl http://localhost:8000/dashboard` — minimal web dashboard

Detaylı scope, fiyatlandırma, KPI ve riskler: **[`PILOT_PITCH.md`](./PILOT_PITCH.md)**

İletişim: a.hakan_@hotmail.com
