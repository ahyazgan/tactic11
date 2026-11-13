# api/

FastAPI uygulaması. Panelin ve dış istemcilerin konuştuğu tek katman.

**Bağımlılık yönü:** `api → agents/ai → engine → domain`. API adaptörleri doğrudan çağırmaz;
veri çekimi `scripts/` ve `scheduler/` üzerinden olur.

**Giriş noktası:** `main.py` uygulamayı kurar ve yönlendiricileri bağlar.

**Yönlendirici grupları:**

| Konu | Dosyalar |
|---|---|
| Kimlik ve kiracı | `auth.py` (JWT, çok kiracılı) |
| Analiz uçları | `main.py`, `sprint3.py`, `sprint4.py`, `sprint5.py`, `context_pipeline.py`, `plan.py` |
| Canlı maç | `live.py` (WebSocket), `live_vaep.py`, `live_provider.py`, `live_feed_factory.py`, `live_service_bridge.py`, `live_shape_bridge.py`, `match_squad.py` |
| Video ve takip | `tracking.py`, `tracking_jobs.py`, `camera_feed.py`, `replay_feed.py`, `review_uploads.py` |
| Rapor ve paylaşım | `reports.py`, `match_reports.py`, `shared.py`, `html_views.py` |
| Fiziksel test | `physical_tests.py` |
| Operasyon | `admin.py`, `notifications.py`, `notes.py`, `sportmonks_catalog.py` |
| Altyapı | `errors.py`, `observability.py` (istek gözlemi, hız sınırı), `pagination.py`, `schemas.py`, `serialize.py` |

**Kurallar:**
- Motor sonucu `serialize.py` ile yanıta çevrilir; motor API şeklini bilmez.
- Her uç kiracıya göre yalıtılır; kimlik `auth.py` üzerinden gelir.
- Hata yanıtları `errors.py` biçimindedir.

**Video işi (`tracking_jobs.py`):** işçi ayrı `venv-cv` yorumlayıcısında alt süreç olarak
koşar, işler tek işçiyle sırayla yürür. Uzun video parçalı işlenir. Ayrılabilir bellek
yetmiyorsa iş, işçi başlamadan açık sebeple `failed` olur (`core/system_resources.py`);
sıfır kare üreten iş de `failed` biter.
