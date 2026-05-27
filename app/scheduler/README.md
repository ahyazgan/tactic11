# scheduler/

Kayıtlı job'lar + retry'lı runner + audit (`job_runs` tablosu).

**Yapı:**
- `registry.py` — `JobSpec` katalog (`register()` ile dolar, `get(name)` ile çözüm)
- `jobs.py` — handler tanımları; modül ilk import edildiğinde kayıt side effect'i
- `runner.py` — `run_job(name, **kwargs)`; bir çağrı = bir `job_runs` satırı;
  exception'da exponential backoff (2s, 4s, 8s) ile `max_attempts`'e kadar dener
- `scripts/run_job.py` — dış cron'un tetiklediği CLI

**Çalıştırma:** zamanlama dış cron/systemd ile. Tek-process daemon yok; tetik
geldiğinde job çalışır, biter, kayıt düşer. Ufuk 3'te `agents/` aynı runner'ı
kullanır.

**Yeni iş ekleme:**
1. `jobs.py`'de bir handler fonksiyonu yaz (`def my_job_handler(**kwargs): ...`)
2. Aynı dosyanın sonunda `register(JobSpec(name="my_job", handler=...))`
3. `scripts/run_job.py`'de o job'a özgü argümanları parse edecek bir dal ekle
