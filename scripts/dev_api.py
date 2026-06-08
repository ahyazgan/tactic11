"""Tek-komut dev backend launcher.

`npm run dev` bunu çağırır: env'i ayarlar (yerel sqlite demo.db), demo veriyi
garanti eder, sonra uvicorn'u 0.0.0.0:8000'de başlatır (0.0.0.0 → tablet de aynı
Wi-Fi'den erişebilir). Manuel env/komut gerekmez.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Windows konsolu cp1254 (Türkçe) olabilir → arrow/em-dash gibi karakterler
# UnicodeEncodeError verir. stdout/stderr'i utf-8'e çevir (app logları da güvenli).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
# Script dosyası olarak çalıştırılınca (python ..\scripts\dev_api.py) proje kökü
# sys.path'te değil → `scripts` ve `app` import edilemez. Kökü ekle.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# Env defaults — kullanıcı dışarıdan set ederse onlar geçerli kalır.
os.environ.setdefault("DATABASE_URL", "sqlite:///" + (ROOT / "demo.db").as_posix())
os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

PORT = int(os.environ.get("DEV_API_PORT", "8000"))


def main() -> None:
    from scripts.dev_seed import ensure_demo_data

    print(f"[dev_api] DB: {os.environ['DATABASE_URL']}")
    print(f"[dev_api] veri: {ensure_demo_data()}")
    print(f"[dev_api] backend -> http://localhost:{PORT}  (LAN: 0.0.0.0:{PORT})")

    import uvicorn

    uvicorn.run("app.api.main:app", host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
