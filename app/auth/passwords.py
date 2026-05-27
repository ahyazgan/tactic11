"""bcrypt password hashing + verify.

bcrypt 5.x: `hashpw(password, salt)` ve `checkpw(password, hash)` API'si.
Default 12 rounds (~250ms hash). Yüksek round sayısı kullanıcı login'ini
yavaşlatır; düşük round sayısı brute-force kolaylaştırır — 12 dengelemesi.

Hash'ler asla loglanmaz; password parametresi de log'a girmemeli (caller'a güven).
"""

from __future__ import annotations

import bcrypt

BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    """bcrypt hash döner (60 karakter, salt dahil).

    Empty password → ValueError (boş şifre kabul etme).
    """
    if not password:
        raise ValueError("password boş olamaz")
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Sabit-zamanlı karşılaştırma (bcrypt.checkpw bunu garanti eder)."""
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        # Bozuk hash formatı — sızdırma vermemek için False
        return False
