"""Engine çıktısı → Claude prompt şablonları.

Engine'in döndürdüğü `EngineResult` (value + AuditRecord) bu modülde stabil bir
JSON gövdesine sarılır ve user prompt'a yapıştırılır. Sistem promptu sabittir,
prompt caching için aynı bayt dizisi olmalıdır — değiştirmeden önce iki kez
düşünün.
"""

from __future__ import annotations

import json

from app.audit import EngineResult

SYSTEM_PROMPT = """Sen futbol teknik ekibine veriyle karar desteği veren bir analiz asistanısın.

Görevin: motor çıktısındaki sayıları kısa, somut, gerekçeli bir cümleyle özetlemek.

Kurallar:
- En fazla 2-3 cümle.
- Sayıları olduğu gibi kullan; uydurma.
- "Form yüksek" gibi soyut yerine "son 5 maçta 3 galibiyet, ppg 1.8" gibi somut konuş.
- Türkçe yaz.
- Veride şüphe veya belirsizlik varsa "veri yetersiz" diyebilirsin; spekülasyon yapma.
"""


def build_user_prompt(result: EngineResult) -> str:
    """EngineResult'ı JSON gövdesi olarak user prompt'a sarar."""
    payload = {
        "engine": result.audit.engine,
        "engine_version": result.audit.engine_version,
        "subject_type": result.audit.subject_type,
        "subject_id": result.audit.subject_id,
        "metric": result.audit.metric,
        "value": result.audit.value,
        "formula": result.audit.formula,
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return f"Motor çıktısı (JSON):\n{body}\n\nBu çıktıyı kısa bir yorumla özetle."


def stub_response(result: EngineResult) -> str:
    """API anahtarı yokken deterministik yer tutucu cevap.

    Üretim çıktısı değil — test/dev'de tüm zincirin çalıştığını göstermek için.
    """
    return (
        f"[stub:{result.audit.engine} v{result.audit.engine_version}] "
        f"{result.audit.subject_type}:{result.audit.subject_id} "
        f"{result.audit.metric} — ANTHROPIC_API_KEY tanımlı değil."
    )
