"""Independent live segments must not manufacture person or camera continuity."""
from __future__ import annotations

import json

import numpy as np
import pytest

from app.tracking.identity_namespace import (
    LOCAL_ID_STRIDE,
    MAX_SAFE_INTEGER,
    PERIOD_STRIDE_MILLISECONDS,
    SegmentIdentityNamespace,
    scope_local_id,
    segment_namespace,
)


def test_first_period_zero_offset_preserves_legacy_ids():
    scope = SegmentIdentityNamespace(period=1, clip_offset_minutes=0)
    assert scope.namespace == 0
    assert scope.scope_track_id(73) == 73
    assert scope.scope_continuity_id(0) == 0


def test_independently_reset_trackers_cannot_share_ids_across_segments():
    previous = SegmentIdentityNamespace(1, 10)
    following = SegmentIdentityNamespace(1, 10.5)
    assert previous.scope_track_id(1) != following.scope_track_id(1)
    assert previous.scope_continuity_id(0) != following.scope_continuity_id(0)
    assert previous.scope_track_id(999_999) < following.scope_track_id(0)


def test_match_periods_have_disjoint_namespaces_at_same_start():
    scopes = [SegmentIdentityNamespace(period, 0) for period in range(1, 6)]
    assert len({scope.scope_track_id(1) for scope in scopes}) == 5
    assert len({scope.scope_continuity_id(0) for scope in scopes}) == 5


def test_millisecond_neighbors_cannot_collide_at_local_id_boundaries():
    earlier, later = SegmentIdentityNamespace(1, 0), SegmentIdentityNamespace(1, 1 / 60_000)
    assert earlier.scope_track_id(999_999) + 1 == later.scope_track_id(0)
    assert scope_local_id(2, 0) != scope_local_id(1, 999_999)


def test_warm_isolated_and_restarted_calls_are_deterministic_for_same_inputs():
    offset = 37_123 / 60_000
    warm = SegmentIdentityNamespace(2, offset)
    isolated = SegmentIdentityNamespace(2, float(repr(offset)))
    restarted = SegmentIdentityNamespace(2, offset)
    assert warm.scope_track_id(54) == isolated.scope_track_id(54) == restarted.scope_track_id(54)
    assert warm.scope_continuity_id(4) == isolated.scope_continuity_id(4) == restarted.scope_continuity_id(4)


def test_largest_admitted_values_remain_exact_in_json_and_javascript_numbers():
    scope = SegmentIdentityNamespace(5, (PERIOD_STRIDE_MILLISECONDS - 1) / 60_000)
    identity = scope.scope_track_id(LOCAL_ID_STRIDE - 1)
    assert identity < MAX_SAFE_INTEGER
    assert int(float(identity)) == identity
    assert json.loads(json.dumps({"player_external_id": identity}))['player_external_id'] == identity
    # build_frame adds this pre-existing video-player base after track scoping.
    assert identity + 30_000 <= MAX_SAFE_INTEGER


@pytest.mark.parametrize("period", [0, -1, 6, 100, 1.0, True])
def test_invalid_match_period_is_rejected(period):
    with pytest.raises(ValueError, match="period"):
        SegmentIdentityNamespace(period, 0)


@pytest.mark.parametrize("offset", [-.001, float("nan"), float("inf"), -float("inf"), True])
def test_invalid_offset_is_rejected(offset):
    with pytest.raises(ValueError, match="finite and nonnegative"):
        SegmentIdentityNamespace(1, offset)


@pytest.mark.parametrize("offset", [1440, 2880, 1e300])
def test_offsets_cannot_overlap_the_next_period_namespace(offset):
    with pytest.raises(ValueError, match="24 hours"):
        SegmentIdentityNamespace(1, offset)


def test_submillisecond_starts_are_rejected_instead_of_silently_colliding():
    with pytest.raises(ValueError, match="whole millisecond"):
        SegmentIdentityNamespace(1, .0005 / 60)
    assert segment_namespace(1, 1 / 3) == 20_000


@pytest.mark.parametrize("local_id", [-1, 1_000_000, 2**53, 1.0, True])
def test_invalid_local_id_is_rejected_instead_of_truncated(local_id):
    scope = SegmentIdentityNamespace(1, 1)
    with pytest.raises(ValueError, match="local identity"):
        scope.scope_track_id(local_id)
    with pytest.raises(ValueError, match="local identity"):
        scope.scope_continuity_id(local_id)


def test_numpy_integer_ids_are_encoded_as_builtin_integers():
    scope = SegmentIdentityNamespace(np.int64(1), 0)
    identity = scope.scope_track_id(np.int64(77))
    assert type(identity) is int and identity == 77


def test_overflow_and_accidental_double_scoping_fail_explicitly():
    with pytest.raises(ValueError, match="JavaScript safe integer"):
        scope_local_id(MAX_SAFE_INTEGER, 0)
    scope = SegmentIdentityNamespace(1, 1)
    with pytest.raises(ValueError, match="local identity"):
        scope.scope_track_id(scope.scope_track_id(1))
