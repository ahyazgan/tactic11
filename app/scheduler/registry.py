"""Kayıtlı işlerin kataloğu.

Job = isim + handler fonksiyonu. Modül ilk import'unda registrelar dolar
(side effect olarak). Runner adıyla bir job çağırır; bilinmeyen ada
`KeyError` fırlar.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JobSpec:
    name: str
    handler: Callable[..., Any]
    description: str = ""


_REGISTRY: dict[str, JobSpec] = {}


def register(spec: JobSpec) -> None:
    if spec.name in _REGISTRY:
        raise ValueError(f"job zaten kayıtlı: {spec.name}")
    _REGISTRY[spec.name] = spec


def get(name: str) -> JobSpec:
    if name not in _REGISTRY:
        raise KeyError(f"bilinmeyen job: {name}")
    return _REGISTRY[name]


# `resolve` — `get` için anlamsal alias (ada göre JobSpec çöz). Bazı çağıranlar
# ve testler bu adı kullanır.
resolve = get


def all_jobs() -> list[JobSpec]:
    return list(_REGISTRY.values())
