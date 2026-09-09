"""Script paketi — ortak konsol kurulumu.

Windows'ta stdout bir boruya/dosyaya yazarken Python yerel kod sayfasını
(burada cp1254) kullanır; scriptlerin çıktısındaki `✓ ⚠ → ✗` gibi karakterler
o tabloda olmadığı için `UnicodeEncodeError` fırlatır ve script ÖLÜR. Konsolda
sorun çıkmaz, yalnız `> log.txt` ya da `| grep` ile çalıştırınca patlar — canlı
maçta log'a yazan `track_live` için gerçek bir risk (bkz. scripts/track_live.py).

Bu modül `python -m scripts.X` çağrılarında her zaman ilk yüklenen yerdir;
akışları UTF-8'e çevirerek tüm scriptleri tek noktadan korur. Terminal UTF-8'i
göstermiyorsa `errors="replace"` sayesinde karakter bozulur ama script yaşar.
"""
from __future__ import annotations

import contextlib
import sys

for _stream in (sys.stdout, sys.stderr):
    # pytest/StringIO gibi reconfigure'ü olmayan akışlarda sessizce geç
    _rc = getattr(_stream, "reconfigure", None)
    if _rc is None:
        continue
    # kapalı ya da yeniden yapılandırılamaz akış — çıktı kodlaması uğruna
    # scripti düşürmenin anlamı yok
    with contextlib.suppress(ValueError, OSError):
        _rc(encoding="utf-8", errors="replace")
