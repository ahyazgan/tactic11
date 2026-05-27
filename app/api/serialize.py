"""Engine sonucunu API yanıtına çevir.

`EngineResult.value` frozen dataclass; FastAPI Pydantic bekler. Burası ikisinin
arasındaki ince adaptör — domain'i Pydantic'e gömmüyoruz (engine pure kalsın),
schema duplikasyonu da yapmıyoruz.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from app.audit import EngineResult


def engine_result_to_dict(result: EngineResult) -> dict[str, Any]:
    value = asdict(result.value) if is_dataclass(result.value) else result.value
    return {
        "value": value,
        "audit": {
            "engine": result.audit.engine,
            "engine_version": result.audit.engine_version,
            "subject_type": result.audit.subject_type,
            "subject_id": result.audit.subject_id,
            "metric": result.audit.metric,
            "formula": result.audit.formula,
            "inputs": result.audit.inputs,
        },
    }
