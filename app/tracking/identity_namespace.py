"""Deterministic, match-scoped namespaces for independently tracked video clips.

Replaying one segment preserves its IDs; another start time or match period
receives a disjoint range. This isolates anonymous estimates, not cross-segment
person re-identification. The first period at offset zero preserves legacy IDs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from numbers import Integral, Real

MAX_SAFE_INTEGER = (1 << 53) - 1
LOCAL_ID_STRIDE = 1_000_000
PERIOD_STRIDE_MILLISECONDS = 24 * 60 * 60 * 1000
MAX_PERIOD = 5  # regulation halves, two extra-time periods, penalty shootout


def _integer(value: int, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    integer = int(value)
    if not minimum <= integer <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return integer


def segment_namespace(period: int, clip_offset_minutes: float) -> int:
    """Encode period and a nonnegative whole-millisecond segment start.

    Period-local offsets must be below 24 hours, keeping period ranges disjoint.
    Tiny floating arithmetic error is tolerated; sub-millisecond starts are
    rejected instead of silently mapping distinct starts to the same namespace.
    """
    period = _integer(period, "period", minimum=1, maximum=MAX_PERIOD)
    if (isinstance(clip_offset_minutes, bool) or not isinstance(clip_offset_minutes, Real)
            or not math.isfinite(clip_offset_minutes) or clip_offset_minutes < 0):
        raise ValueError("clip offset must be finite and nonnegative")
    milliseconds = float(clip_offset_minutes) * 60_000
    if not math.isfinite(milliseconds) or milliseconds >= PERIOD_STRIDE_MILLISECONDS:
        raise ValueError("clip offset must be below 24 hours")
    start = round(milliseconds)
    if not math.isclose(milliseconds, start, rel_tol=0, abs_tol=1e-6):
        raise ValueError("clip offset must resolve to a whole millisecond")
    if not 0 <= start < PERIOD_STRIDE_MILLISECONDS:
        raise ValueError("rounded clip offset exceeds its period namespace")
    return (period - 1) * PERIOD_STRIDE_MILLISECONDS + start


def scope_local_id(namespace: int, local_id: int) -> int:
    """Encode an ID without hash collisions, truncation or JavaScript overflow."""
    namespace = _integer(namespace, "namespace", minimum=0, maximum=MAX_SAFE_INTEGER)
    local_id = _integer(local_id, "local identity", minimum=0, maximum=LOCAL_ID_STRIDE - 1)
    scoped = namespace * LOCAL_ID_STRIDE + local_id
    if scoped > MAX_SAFE_INTEGER:
        raise ValueError("scoped identity exceeds the JavaScript safe integer range")
    return scoped


@dataclass(frozen=True)
class SegmentIdentityNamespace:
    """Validated segment scope, reusable for every player and camera epoch."""

    period: int
    clip_offset_minutes: float
    namespace: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "namespace", segment_namespace(self.period, self.clip_offset_minutes))

    def scope_track_id(self, local_track_id: int) -> int:
        return scope_local_id(self.namespace, local_track_id)

    def scope_continuity_id(self, local_continuity_id: int) -> int:
        return scope_local_id(self.namespace, local_continuity_id)
