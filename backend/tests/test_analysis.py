"""Timing vs size decomposition, and data-quality reporting."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analysis import biggest_misses, data_quality, decompose_timing_vs_size

UTC = "UTC"
START = pd.Timestamp("2026-01-05T00:00Z")


def _joined(forecast, actual, freq="1h"):
    idx = pd.date_range(START, periods=len(forecast), freq=freq, tz=UTC)
    df = pd.DataFrame(
        {
            "startTime": idx,
            "cutoff": idx - pd.Timedelta(hours=12),
            "publishTime": idx - pd.Timedelta(hours=12),
            "lead_h": 12.0,
            "forecast_mw": np.asarray(forecast, dtype=float),
            "actual_mw": np.asarray(actual, dtype=float),
            "reason": "ok",
        }
    )
    df["error"] = df["forecast_mw"] - df["actual_mw"]
    df["abs_error"] = df["error"].abs()
    return df


def test_pure_timing_error_is_labelled_timing():
    """A ramp forecast two hours early: same shape, wrong time."""
    ramp = [1000, 1000, 2000, 6000, 10000, 10000, 10000, 10000, 10000, 10000]
    actual = [1000, 1000, 1000, 1000, 2000, 6000, 10000, 10000, 10000, 10000]
    joined = _joined(ramp, actual)
    target = START + pd.Timedelta(hours=4)

    d = decompose_timing_vs_size(joined, target)
    assert d["miss_type"] == "timing"
    assert d["best_shift_h"] == 2.0  # forecast must move 2h later
    assert d["error_removed_by_shift_pct"] > 50.0
    assert d["window_mae_at_best_shift_mw"] < d["window_mae_unshifted_mw"]


def test_pure_size_error_is_labelled_size():
    """Flat 3000 MW too high everywhere: no shift can help."""
    joined = _joined([13000] * 10, [10000] * 10)
    d = decompose_timing_vs_size(joined, START + pd.Timedelta(hours=4))
    assert d["miss_type"] == "size"
    assert d["best_shift_h"] == 0.0
    assert d["error_removed_by_shift_pct"] == pytest.approx(0.0)


def test_shift_curve_is_reported_for_every_candidate_shift():
    joined = _joined([13000] * 10, [10000] * 10)
    d = decompose_timing_vs_size(joined, START + pd.Timedelta(hours=4))
    assert set(d["shift_curve_mw"]) == {-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0}


def test_decomposition_degrades_gracefully_with_no_data():
    empty = _joined([np.nan], [np.nan])
    d = decompose_timing_vs_size(empty, START)
    assert d["miss_type"] == "unknown"
    assert d["decomposition_note"] is not None


def test_biggest_misses_ranks_by_absolute_error_and_decomposes_each():
    forecast = [10000, 10000, 10000, 15000, 10000, 10000, 10000, 10000]
    actual = [10000, 10000, 10000, 10000, 9000, 10000, 10000, 10000]
    out = biggest_misses(_joined(forecast, actual), n=2)

    assert len(out) == 2
    assert out.iloc[0]["abs_error"] == 5000.0
    assert out.iloc[1]["abs_error"] == 1000.0
    assert out["abs_error"].is_monotonic_decreasing
    assert set(out["miss_type"]) <= {"timing", "size", "unknown"}
    assert out.iloc[0]["error"] == 5000.0  # positive = over-forecast


def test_miss_at_the_window_edge_is_still_decomposed_via_context():
    """A miss in the last period of a slice has no +3h neighbours inside it.

    A flat level error is used rather than a single spike: shifting a lone spike
    around a short series is genuinely ambiguous, so it would not isolate the
    behaviour under test.
    """
    # uniformly 3000 MW too high, with the slice's last period slightly worse so
    # it ranks first
    forecast = [13000] * 10
    forecast[3] = 14000
    full = _joined(forecast, [10000] * 10)
    window = full.iloc[:4]  # the miss sits on the final row of the slice

    without = biggest_misses(window, n=1)
    assert without.iloc[0]["startTime"] == window.iloc[3]["startTime"]
    assert without.iloc[0]["miss_type"] == "unknown"
    assert without.iloc[0]["decomposition_note"] == "insufficient overlap"

    with_context = biggest_misses(window, n=1, context=full)
    assert with_context.iloc[0]["miss_type"] == "size"
    assert with_context.iloc[0]["decomposition_note"] is None
    # no shift gets close to removing half the local error, which is the rule
    assert with_context.iloc[0]["error_removed_by_shift_pct"] < 50.0
    assert len(with_context.iloc[0]["shift_curve_mw"]) == 7
    # ranking still comes from the window, not from the wider context
    assert with_context.iloc[0]["startTime"] == window.iloc[3]["startTime"]


def test_biggest_misses_ignores_periods_with_no_forecast():
    joined = _joined([np.nan, 10000, 12000], [10000, 10000, 10000])
    out = biggest_misses(joined, n=5)
    assert len(out) == 2
    assert joined["startTime"].iloc[0] not in set(out["startTime"])


def test_data_quality_reports_a_real_gap():
    actuals = pd.DataFrame(
        {
            "startTime": pd.date_range("2026-01-01T00:00Z", periods=4, freq="30min"),
            "generation": [100.0, 200.0, 300.0, 400.0],
        }
    )
    forecasts = pd.DataFrame(
        {
            "startTime": pd.date_range("2026-01-01T00:00Z", periods=2, freq="1h"),
            "publishTime": pd.Timestamp("2025-12-31T09:30Z"),
            "generation": [150.0, 350.0],
        }
    )
    report = {
        "target_window_utc": ["2026-01-01T00:00:00+00:00", "2026-01-01T03:00:00+00:00"],
    }
    dq = data_quality(report, actuals, forecasts)

    live = dq["live_checks"]
    assert live["actual_periods_expected"] == 6
    assert live["actual_rows"] == 4
    assert len(live["actual_periods_missing"]) == 2
    assert live["actual_coverage_pct"] == pytest.approx(100.0 * 4 / 6)
    assert live["forecast_duplicate_keys"] == 0
    assert live["forecast_negative_lead_rows"] == 0
    assert "missing_intervals" in dq["handling"]
    assert len(dq["coverage_per_day"]) == 1
