"""Kuralları öğe listelerine uygulayan çalıştırıcı.

Reddedilen kayıt sessizce ATILMAZ: loglanır ve `ValidationResult.rejected`
içinde hata mesajıyla birlikte taşınır. Üst katman bunu izleyebilir.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Generic, TypeVar

from app.core.logging import get_logger
from app.data.validation.rules import LEAGUE_RULES, MATCH_RULES, TEAM_RULES
from app.domain import League, Match, Team

log = get_logger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class ValidationResult(Generic[T]):
    accepted: list[T]
    rejected: list[tuple[T, list[str]]]


def _run(rules: tuple[Callable[[T], list[str]], ...], items: Iterable[T]) -> ValidationResult[T]:
    accepted: list[T] = []
    rejected: list[tuple[T, list[str]]] = []
    for item in items:
        errors: list[str] = []
        for rule in rules:
            errors.extend(rule(item))
        if errors:
            log.warning("validation reject %s: %s", type(item).__name__, errors)
            rejected.append((item, errors))
        else:
            accepted.append(item)
    return ValidationResult(accepted=accepted, rejected=rejected)


def validate_leagues(items: Iterable[League]) -> ValidationResult[League]:
    return _run(LEAGUE_RULES, items)


def validate_teams(items: Iterable[Team]) -> ValidationResult[Team]:
    return _run(TEAM_RULES, items)


def validate_matches(items: Iterable[Match]) -> ValidationResult[Match]:
    return _run(MATCH_RULES, items)
