"""Tests for the core rule. The no-lookahead property test is the load-bearing one."""

from __future__ import annotations

from datetime import time

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.selection import (
    REASON_ALL_FORECASTS_AFTER_CUTOFF,
    REASON_NO_FORECAST_FOR_TARGET,
    REASON_OFF_FORECAST_GRID,
    REASON_OK,
    compute_cutoffs,
    forecast_vintages,
    select_live_forecasts,
)

UTC = "UTC"


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz=UTC)


def fc(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """Build a WINDFOR frame from (startTime, publishTime, generation) tuples."""
    return pd.DataFrame(
        {
            "startTime": [ts(r[0]) for r in rows],
            "publishTime": [ts(r[1]) for r in rows],
            "generation": [r[2] for r in rows],
        }
    )


# --------------------------------------------------------------------------- #
# 1. a forecast published after the cutoff is skipped
# --------------------------------------------------------------------------- #
def test_forecast_published_after_cutoff_is_skipped():
    forecasts = fc(
        [
            ("2026-01-10T12:00Z", "2026-01-09T06:00Z", 1000.0),
            ("2026-01-10T12:00Z", "2026-01-10T00:00Z", 2000.0),  # live at T-12h
            ("2026-01-10T12:00Z", "2026-01-10T10:00Z", 3000.0),  # too late
        ]
    )
    out = select_live_forecasts(forecasts, [ts("2026-01-10T12:00Z")], "horizon", 12)

    assert len(out) == 1
    row = out.iloc[0]
    assert row["cutoff"] == ts("2026-01-10T00:00Z")
    assert row["publishTime"] == ts("2026-01-10T00:00Z")
    assert row["forecast_mw"] == 2000.0
    assert row["lead_h"] == 12.0
    assert row["reason"] == REASON_OK


def test_only_forecast_is_after_cutoff_so_previous_is_used_even_if_stale():
    """A very old vintage still wins over one published past the cutoff."""
    forecasts = fc(
        [
            ("2026-01-10T12:00Z", "2026-01-01T00:00Z", 500.0),
            ("2026-01-10T12:00Z", "2026-01-10T11:00Z", 4000.0),
        ]
    )
    out = select_live_forecasts(forecasts, [ts("2026-01-10T12:00Z")], "horizon", 6)
    assert out.iloc[0]["forecast_mw"] == 500.0
    assert out.iloc[0]["lead_h"] == pytest.approx(9 * 24 + 12)


# --------------------------------------------------------------------------- #
# 2. publish exactly at the cutoff is allowed
# --------------------------------------------------------------------------- #
def test_publish_exactly_at_cutoff_is_allowed():
    forecasts = fc(
        [
            ("2026-01-10T12:00Z", "2026-01-09T23:59Z", 1000.0),
            ("2026-01-10T12:00Z", "2026-01-10T00:00Z", 2000.0),  # == cutoff
        ]
    )
    out = select_live_forecasts(forecasts, [ts("2026-01-10T12:00Z")], "horizon", 12)
    assert out.iloc[0]["publishTime"] == ts("2026-01-10T00:00Z")
    assert out.iloc[0]["forecast_mw"] == 2000.0


def test_one_second_after_cutoff_is_not_allowed():
    forecasts = fc(
        [
            ("2026-01-10T12:00Z", "2026-01-09T23:59Z", 1000.0),
            ("2026-01-10T12:00:01Z", "2026-01-10T00:00:01Z", 2000.0),
        ]
    )
    forecasts.loc[1, "startTime"] = ts("2026-01-10T12:00Z")
    out = select_live_forecasts(forecasts, [ts("2026-01-10T12:00Z")], "horizon", 12)
    assert out.iloc[0]["publishTime"] == ts("2026-01-09T23:59Z")
    assert out.iloc[0]["forecast_mw"] == 1000.0


# --------------------------------------------------------------------------- #
# 3. no eligible forecast -> null plus a reason, row is kept
# --------------------------------------------------------------------------- #
def test_no_forecast_at_all_for_target_keeps_row_with_reason():
    forecasts = fc([("2026-01-10T12:00Z", "2026-01-09T06:00Z", 1000.0)])
    targets = [ts("2026-01-10T12:00Z"), ts("2026-01-11T12:00Z")]
    out = select_live_forecasts(forecasts, targets, "horizon", 12)

    assert len(out) == 2  # nothing silently dropped
    assert list(out["startTime"]) == targets
    assert out.iloc[1]["reason"] == REASON_NO_FORECAST_FOR_TARGET
    assert pd.isna(out.iloc[1]["forecast_mw"])
    assert pd.isna(out.iloc[1]["publishTime"])
    assert pd.isna(out.iloc[1]["lead_h"])
    assert out.iloc[1]["cutoff"] == ts("2026-01-11T00:00Z")  # cutoff still reported


def test_all_forecasts_published_after_cutoff_is_a_distinct_reason():
    forecasts = fc([("2026-01-10T12:00Z", "2026-01-10T06:00Z", 1000.0)])
    out = select_live_forecasts(forecasts, [ts("2026-01-10T12:00Z")], "horizon", 24)
    assert out.iloc[0]["reason"] == REASON_ALL_FORECASTS_AFTER_CUTOFF
    assert pd.isna(out.iloc[0]["forecast_mw"])


def test_empty_forecast_frame_keeps_every_target():
    empty = fc([]).astype({"generation": "float64"})
    targets = pd.date_range("2026-01-01", periods=5, freq="30min", tz=UTC)
    out = select_live_forecasts(empty, targets, "horizon", 12)
    assert len(out) == 5
    assert set(out["reason"]) == {REASON_NO_FORECAST_FOR_TARGET}


# --------------------------------------------------------------------------- #
# 4. horizon 0
# --------------------------------------------------------------------------- #
def test_horizon_zero_uses_everything_published_up_to_delivery_start():
    forecasts = fc(
        [
            ("2026-01-10T12:00Z", "2026-01-10T11:00Z", 1000.0),
            ("2026-01-10T12:00Z", "2026-01-10T12:00Z", 2000.0),  # == T, allowed
            ("2026-01-10T12:00Z", "2026-01-10T12:30Z", 3000.0),  # after T, never
        ]
    )
    out = select_live_forecasts(forecasts, [ts("2026-01-10T12:00Z")], "horizon", 0)
    assert out.iloc[0]["cutoff"] == ts("2026-01-10T12:00Z")
    assert out.iloc[0]["forecast_mw"] == 2000.0
    assert out.iloc[0]["lead_h"] == 0.0


def test_negative_horizon_is_rejected():
    with pytest.raises(ValueError, match="horizon_h must be >= 0"):
        select_live_forecasts(fc([]), [ts("2026-01-10T12:00Z")], "horizon", -1)


# --------------------------------------------------------------------------- #
# 5. day-ahead mode, including across the London midnight boundary
# --------------------------------------------------------------------------- #
def test_day_ahead_cutoff_is_previous_london_day_at_configured_time():
    targets = [ts("2026-01-10T00:00Z"), ts("2026-01-10T23:30Z")]
    cutoffs = compute_cutoffs(targets, "day_ahead", cutoff_local_time=time(9, 20))
    # January: London == UTC, so both delivery periods fall on the 10th and
    # share one cutoff on the 9th.
    assert list(cutoffs) == [ts("2026-01-09T09:20Z"), ts("2026-01-09T09:20Z")]


def test_day_ahead_delivery_day_is_london_not_utc_across_midnight():
    """23:30 UTC in BST is already the next London day: cutoff moves a day too."""
    targets = [ts("2026-07-09T22:30Z"), ts("2026-07-09T23:30Z")]
    cutoffs = compute_cutoffs(targets, "day_ahead", cutoff_local_time=time(9, 20))
    # 22:30Z = 23:30 London on the 9th -> cutoff 09:20 London on the 8th = 08:20Z
    # 23:30Z = 00:30 London on the 10th -> cutoff 09:20 London on the 9th = 08:20Z
    assert cutoffs[0] == ts("2026-07-08T08:20Z")
    assert cutoffs[1] == ts("2026-07-09T08:20Z")


def test_day_ahead_mode_selects_across_midnight_boundary():
    forecasts = fc(
        [
            # target 00:30 on the 10th, delivery day = 10 Jan, cutoff 9 Jan 09:20
            ("2026-01-10T00:00Z", "2026-01-09T08:00Z", 1500.0),
            ("2026-01-10T00:00Z", "2026-01-09T09:20Z", 1600.0),  # exactly at gate
            ("2026-01-10T00:00Z", "2026-01-09T10:00Z", 9999.0),  # after gate
            # target 23:30 on the 9th, delivery day = 9 Jan, cutoff 8 Jan 09:20
            ("2026-01-09T23:00Z", "2026-01-08T09:00Z", 700.0),
            ("2026-01-09T23:00Z", "2026-01-09T09:00Z", 8888.0),  # after gate
        ]
    )
    targets = [ts("2026-01-09T23:30Z"), ts("2026-01-10T00:30Z")]
    out = select_live_forecasts(
        forecasts, targets, "day_ahead", cutoff_local_time=time(9, 20), alignment="hold"
    )
    assert list(out["forecast_mw"]) == [700.0, 1600.0]
    assert list(out["cutoff"]) == [ts("2026-01-08T09:20Z"), ts("2026-01-09T09:20Z")]
    assert list(out["reason"]) == [REASON_OK, REASON_OK]


def test_day_ahead_cutoff_time_is_configurable():
    forecasts = fc(
        [
            ("2026-01-10T12:00Z", "2026-01-09T09:20Z", 1000.0),
            ("2026-01-10T12:00Z", "2026-01-09T09:50Z", 2000.0),
        ]
    )
    at_epex = select_live_forecasts(
        forecasts, [ts("2026-01-10T12:00Z")], "day_ahead", cutoff_local_time=time(9, 20)
    )
    at_n2ex = select_live_forecasts(
        forecasts, [ts("2026-01-10T12:00Z")], "day_ahead", cutoff_local_time=time(9, 50)
    )
    assert at_epex.iloc[0]["forecast_mw"] == 1000.0
    assert at_n2ex.iloc[0]["forecast_mw"] == 2000.0


# --------------------------------------------------------------------------- #
# half-hour alignment switch
# --------------------------------------------------------------------------- #
def test_hold_alignment_covers_the_half_hour():
    forecasts = fc([("2026-01-10T12:00Z", "2026-01-09T06:00Z", 1234.0)])
    out = select_live_forecasts(
        forecasts, [ts("2026-01-10T12:30Z")], "horizon", 12, alignment="hold"
    )
    assert out.iloc[0]["forecast_mw"] == 1234.0
    # cutoff = 12:30 - 12h = 00:30 on the 10th, so the 09 Jan 06:00 vintage is live;
    # lead time is measured to the target itself (12:30), not to the forecast hour.
    assert out.iloc[0]["lead_h"] == pytest.approx(30.5)


def test_hourly_points_alignment_reports_half_hours_as_off_grid():
    forecasts = fc([("2026-01-10T12:00Z", "2026-01-09T06:00Z", 1234.0)])
    out = select_live_forecasts(
        forecasts,
        [ts("2026-01-10T12:00Z"), ts("2026-01-10T12:30Z")],
        "horizon",
        12,
        alignment="hourly_points",
    )
    assert out.iloc[0]["reason"] == REASON_OK
    assert out.iloc[1]["reason"] == REASON_OFF_FORECAST_GRID
    assert pd.isna(out.iloc[1]["forecast_mw"])


# --------------------------------------------------------------------------- #
# misc contract
# --------------------------------------------------------------------------- #
def test_naive_timestamps_are_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        select_live_forecasts(fc([]), [pd.Timestamp("2026-01-10T12:00")], "horizon", 12)


def test_duplicate_publish_times_do_not_duplicate_rows():
    forecasts = fc(
        [
            ("2026-01-10T12:00Z", "2026-01-09T06:00Z", 1000.0),
            ("2026-01-10T12:00Z", "2026-01-09T06:00Z", 1000.0),
        ]
    )
    out = select_live_forecasts(forecasts, [ts("2026-01-10T12:00Z")], "horizon", 12)
    assert len(out) == 1
    assert out.iloc[0]["forecast_mw"] == 1000.0


def test_forecast_vintages_marks_the_live_row():
    forecasts = fc(
        [
            ("2026-01-10T12:00Z", "2026-01-08T06:00Z", 1000.0),
            ("2026-01-10T12:00Z", "2026-01-09T06:00Z", 2000.0),
            ("2026-01-10T12:00Z", "2026-01-10T06:00Z", 3000.0),
        ]
    )
    out = forecast_vintages(
        forecasts, ts("2026-01-10T12:30Z"), cutoff=ts("2026-01-09T09:20Z")
    )
    assert len(out) == 3
    assert list(out["eligible"]) == [True, True, False]
    assert list(out["is_live"]) == [False, True, False]
    assert out.loc[out["is_live"], "forecast_mw"].iloc[0] == 2000.0
    assert list(out["lead_h"]) == pytest.approx([54.5, 30.5, 6.5])


# --------------------------------------------------------------------------- #
# THE property test: no lookahead, ever
# --------------------------------------------------------------------------- #
BASE = pd.Timestamp("2026-01-15T12:00Z")

publish_offsets = st.integers(min_value=-240, max_value=24)  # hours around T
target_offsets = st.integers(min_value=-48, max_value=48)  # hours around BASE


@settings(max_examples=300, deadline=None)
@given(
    forecast_rows=st.lists(
        st.tuples(
            st.sampled_from([-24, -12, 0, 12, 24, 36]),  # target offset, hours
            publish_offsets,
            st.floats(min_value=0, max_value=25000, allow_nan=False),
        ),
        min_size=0,
        max_size=40,
    ),
    horizon_h=st.integers(min_value=0, max_value=72),
    target_offsets_chosen=st.lists(target_offsets, min_size=1, max_size=8),
)
def test_never_uses_future_forecasts(forecast_rows, horizon_h, target_offsets_chosen):
    """For every target, the selected publishTime is <= cutoff and is the latest such.

    This is the whole safety property of the app, asserted against a brute-force
    reference computed independently of merge_asof.
    """
    forecasts = pd.DataFrame(
        {
            "startTime": [BASE + pd.Timedelta(hours=o) for o, _, _ in forecast_rows],
            "publishTime": [
                BASE + pd.Timedelta(hours=o) + pd.Timedelta(hours=p)
                for o, p, _ in forecast_rows
            ],
            "generation": [g for _, _, g in forecast_rows],
        }
    )
    # keep dtypes datetime64[ns, UTC] even when hypothesis generates no rows,
    # so the brute-force reference below can compare timestamps
    for col in ("startTime", "publishTime"):
        forecasts[col] = pd.to_datetime(forecasts[col], utc=True)
    targets = [BASE + pd.Timedelta(hours=o) for o in target_offsets_chosen]

    out = select_live_forecasts(
        forecasts, targets, "horizon", horizon_h=horizon_h, alignment="hold"
    )

    assert len(out) == len(targets)
    assert list(out["startTime"]) == targets

    for i, target in enumerate(targets):
        row = out.iloc[i]
        cutoff = target - pd.Timedelta(hours=horizon_h)
        assert row["cutoff"] == cutoff

        # brute-force reference for the same rule
        same_target = forecasts["startTime"] == target.floor("h")
        eligible = forecasts.loc[same_target & (forecasts["publishTime"] <= cutoff)]

        if eligible.empty:
            assert pd.isna(row["publishTime"])
            assert pd.isna(row["forecast_mw"])
            assert row["reason"] != "ok"
        else:
            expected_pub = eligible["publishTime"].max()
            # never after the cutoff
            assert row["publishTime"] <= cutoff
            # and the latest one that qualifies
            assert row["publishTime"] == expected_pub
            # value comes from a row actually published at that time
            candidates = set(
                eligible.loc[eligible["publishTime"] == expected_pub, "generation"]
            )
            assert row["forecast_mw"] in candidates
            assert row["reason"] == "ok"
