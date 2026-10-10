"""Validated human-authored observations. No inferred player statistics."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Finding(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", allow_inf_nan=False)
    id: UUID
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    category: Literal["attack", "defence", "transition", "set_piece", "player"]
    title: str = Field(min_length=1, max_length=140)
    observation: str = Field(min_length=1, max_length=1500)
    action: str = Field(min_length=1, max_length=1000)
    player: str = Field(default="", max_length=120)
    next_check: str = Field(default="", max_length=700)

    @model_validator(mode="after")
    def valid_interval(self) -> Finding:
        if not 0.5 <= self.end - self.start <= 120:
            raise ValueError("Pozisyon 0,5 ile 120 saniye arasında olmalı.")
        return self


class ReviewDocument(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    club: str = Field(default="", max_length=120)
    opponent: str = Field(default="", max_length=120)
    match_date: date | None = None
    scope: Literal["selected_segments", "full_match"] = "selected_segments"
    summary: str = Field(default="", max_length=3000)
    strengths: str = Field(default="", max_length=1500)
    training_focus: list[str] = Field(default_factory=list, max_length=3)
    findings: list[Finding] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def valid_document(self) -> ReviewDocument:
        ids = [f.id for f in self.findings]
        if len(ids) != len(set(ids)):
            raise ValueError("Pozisyon kimlikleri tekrarlanamaz.")
        self.training_focus = [s.strip() for s in self.training_focus if s.strip()]
        if any(len(s) > 700 for s in self.training_focus):
            raise ValueError("Antrenman odağı en fazla 700 karakter olabilir.")
        return self


CATEGORIES = {"attack": "Hücum", "defence": "Savunma", "transition": "Geçiş",
              "set_piece": "Duran top", "player": "Oyuncu gelişimi"}


def time_label(seconds: float) -> str:
    ticks = round(seconds * 10)
    minutes, remainder = divmod(ticks, 600)
    whole, fraction = divmod(remainder, 10)
    return f"{minutes:02d}:{whole:02d}" + (f".{fraction}" if fraction else "")


def review_time_label(value: str) -> str:
    if not value:
        return "Belirtilmedi"
    moment = datetime.fromisoformat(value)
    return moment.replace(tzinfo=moment.tzinfo or UTC).astimezone(UTC).strftime("%d.%m.%Y %H:%M UTC")
