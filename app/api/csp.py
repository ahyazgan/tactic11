"""Content-Security-Policy yardımcıları (Faz 9 #5).

Sunucu-render HTML sayfaları inline `<script>`/`<style>` blokları kullanıyor.
Güçlü CSP için her isteğe özel bir nonce üretir, HTML'deki inline blok
açılış etiketlerine `nonce="..."` enjekte eder ve CSP header'ını aynı nonce
ile kurar. Böylece `'unsafe-inline'` olmadan inline kod çalışır; saldırgan
enjekte ettiği script doğru nonce'u bilemez.

HTML dışı (JSON/PDF) yanıtlar için kaynak yükleme gerekmediğinden çok katı
bir varsayılan policy kullanılır (`STRICT_API_CSP`).
"""

from __future__ import annotations

import re
import secrets

# <script ...> veya <style ...> açılışına (zaten nonce'u yoksa) nonce ekle.
# `</script>` eşleşmez (`<` sonrası `/`). Etiket adından sonra boşluk veya `>`
# gelmesini şart koşarak `<scripting>` gibi yanlış eşleşmeyi önler.
_TAG_RE = re.compile(
    r"<(script|style)(?![^>]*\bnonce=)(?=[\s>])",
    re.IGNORECASE,
)

# HTML olmayan yanıtlar: hiçbir kaynak yüklenmemeli.
STRICT_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def generate_nonce() -> str:
    """Tahmin edilemez, isteğe özel base64url nonce."""
    return secrets.token_urlsafe(16)


def inject_nonce(html: str, nonce: str) -> str:
    """HTML içindeki inline `<script>`/`<style>` açılışlarına nonce ekle."""
    return _TAG_RE.sub(rf'<\1 nonce="{nonce}"', html)


def html_csp_header(nonce: str) -> str:
    """Sunucu-render sayfalar için nonce-tabanlı CSP policy string'i."""
    return (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        f"style-src 'self' 'nonce-{nonce}'; "
        "img-src 'self' data: blob:; "
        "media-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    )


def render_html_with_csp(html: str):
    """HTML'i nonce'la zenginleştir + CSP header'lı HTMLResponse döndür."""
    from fastapi.responses import HTMLResponse

    nonce = generate_nonce()
    body = inject_nonce(html, nonce)
    resp = HTMLResponse(body)
    resp.headers["Content-Security-Policy"] = html_csp_header(nonce)
    return resp
