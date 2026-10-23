"""Metrics against a hand-computed tiny dataset."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.metrics import (
    compute_metrics,
    error_by_hour_of_day,
    error_by_horizon,
    error_by_wind_level,
    join_actuals,
)

UTC = "UTC"


def _joined(forecast, actual, start="2026-01-05T00:00Z", freq="30min"):
    idx = pd.date_range(start, periods=len(forecast), freq=freq, tz=UTC)
    df = pd.DataFrame(
        {
            "startTime": idx,
            "cutoff": idx - pd.Timedelta(hours=12),
            "publishTime": idx - pd.Timedelta(hours=12),
            "lead_h": 12.0,
            "forecast_mw": forecast,
            "actual_mw": actual,
            "reason": "ok",
        }
    )
    df["error"] = df["forecast_mw"] - df["actual_mw"]
    df["abs_error"] = df["error"].abs()
    return df


def test_compute_metrics_known_answers():
    # errors: +100, -200, +300, 0  -> abs: 100, 200, 300, 0
    joined = _joined([1100.0, 800.0, 1300.0, 1000.0], [1000.0, 1000.0, 1000.0, 1000.0])
    m = compute_metrics(joined)

    assert m["count"] == 4
    assert m["coverage_pct"] == 100.0
    assert m["mae_mw"] == pytest.approx((100 + 200 + 300 + 0) / 4)  # 150
    assert m["rmse_mw"] == pytest.approx(np.sqrt((100**2 + 200**2 + 300**2) / 4))  # ~187.08
    assert m["bias_mw"] == pytest.approx((100 - 200 + 300 + 0) / 4)  # +50, over-forecast
    assert m["mean_actual_mw"] == pytest.approx(1000.0)
    assert m["nmae_pct"] == pytest.approx(15.0)
    assert m["p50_abs_error_mw"] == pytest.approx(150.0)  # median of 0,100,200,300
    assert m["p90_abs_error_mw"] == pytest.approx(270.0)  # linear interp
    assert m["mean_actual_mw"] == 1000.0


def test_bias_sign_convention_positive_means_over_forecast():
    over = _joined([1200.0, 1200.0], [1000.0, 1000.0])
    under = _joined([800.0, 800.0], [1000.0, 1000.0])
    assert compute_metrics(over)["bias_mw"] == pytest.approx(200.0)
    assert compute_metrics(under)["bias_mw"] == pytest.approx(-200.0)


def test_metrics_ignore_unscored_rows_but_coverage_reports_them():
    joined = _joined([1100.0, np.nan, 1300.0, 1000.0], [1000.0] * 4)
    m = compute_metrics(joined)
    assert m["count"] == 3
    assert m["coverage_pct"] == pytest.approx(75.0)
    assert m["mae_mw"] == pytest.approx((100 + 300 + 0) / 3)


def test_metrics_on_empty_sample_returns_nulls_not_a_crash():
    joined = _joined([np.nan, np.nan], [1000.0, 1000.0])
    m = compute_metrics(joined)
    assert m["count"] == 0
    assert m["coverage_pct"] == 0.0
    assert m["mae_mw"] is None


def test_nmae_is_stable_where_mape_would_explode():
    """A 50 MW miss on a 10 MW hour: MAPE would say 500%, nMAE stays sane."""
    joined = _joined([60.0, 1000.0], [10.0, 1000.0])
    m = compute_metrics(joined)
    assert m["mae_mw"] == pytest.approx(25.0)
    assert m["mean_actual_mw"] == pytest.approx(505.0)
    assert m["nmae_pct"] == pytest.approx(100.0 * 25.0 / 505.0)
    assert m["nmae_pct"] < 10.0


def test_error_by_hour_of_day_groups_correctly():
    joined = _joined([1100.0] * 4, [1000.0] * 4, start="2026-01-05T00:00Z", freq="1h")
    out = error_by_hour_of_day(joined)
    assert list(out["hour"]) == [0, 1, 2, 3]
    assert set(out["count"]) == {1}
    assert out["mae_mw"].tolist() == pytest.approx([100.0] * 4)


def test_error_by_wind_level_buckets_on_forecast_not_actual():
    joined = _joined([1000.0, 6000.0, 12000.0], [900.0, 6500.0, 11000.0])
    out = error_by_wind_level(joined, edges=(0, 2000, 8000, np.inf))
    assert list(out["count"]) == [1, 1, 1]
    assert out["mae_mw"].tolist() == pytest.approx([100.0, 500.0, 1000.0])


def test_error_by_horizon_runs_a_fresh_no_lookahead_selection_per_horizon():
    actuals = pd.DataFrame(
        {
            "startTime": pd.date_range("2026-01-05T00:00Z", periods=4, freq="1h"),
            "generation": [1000.0, 1000.0, 1000.0, 1000.0],
        }
    )
    # two vintages: an early bad one and a late good one
    forecasts = pd.concat(
        [
            pd.DataFrame(
                {
                    "startTime": actuals["startTime"],
                    "publishTime": actuals["startTime"] - pd.Timedelta(hours=24),
                    "generation": 1500.0,
                }
            ),
            pd.DataFrame(
                {
                    "startTime": actuals["startTime"],
                    "publishTime": actuals["startTime"] - pd.Timedelta(hours=2),
                    "generation": 1050.0,
                }
            ),
        ]
    )
    out = error_by_horizon(forecasts, actuals, horizons=[1, 24])
    at_1h = out.loc[out["horizon_h"] == 1].iloc[0]
    at_24h = out.loc[out["horizon_h"] == 24].iloc[0]
    assert at_1h["mae_mw"] == pytest.approx(50.0)  # saw the fresh vintage
    assert at_24h["mae_mw"] == pytest.approx(500.0)  # only the stale one was allowed
    assert at_1h["coverage_pct"] == 100.0
