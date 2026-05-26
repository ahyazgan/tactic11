# scheduler/  [İSKELET]

**İLERİDE:** günlük otomatik sync buradan tetiklenir. Ufuk 3'te `agents/` de
buraya bağlanır.

**Faz 1'de:** sync elle `scripts/sync_league.py` ile çalışır; bu klasör henüz boş.
İleride o CLI'yi zamanlanmış göreve bağlayacak doğal yer burası.

**Olası seçenekler (henüz karar yok):** APScheduler, cron + entry-point, Celery beat.
