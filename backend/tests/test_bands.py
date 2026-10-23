"""Walk-forward discipline, newsvendor arithmetic, and calibration honesty."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.bands import (
    WEEK,
    assign_week,
    calibration,
    newsvendor_quantile,
    plan_at_cost_ratio,
    plan_on,
    shortfall_summary,
    walk_forward_bands,
)

UTC = "UTC"
START = pd.Timestamp("2026-01-01T00:00Z")


def synthetic_joined(n_days=28, sigma=500.0, seed=0, forecast_mw=10000.0, lead_h=24.0):
    """A month of hourly periods with N(0, sigma) errors around a flat forecast."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(START, periods=n_days * 24, freq="1h", tz=UTC)
    error = rng.normal(0.0, sigma, len(idx))
    df = pd.DataFrame(
        {
            "startTime": idx,
            "cutoff": idx - pd.Timedelta(hours=lead_h),
            "publishTime": idx - pd.Timedelta(hours=lead_h),
            "lead_h": lead_h,
            "forecast_mw": forecast_mw,
            "actual_mw": forecast_mw - error,
            "reason": "ok",
        }
    )
    df["error"] = df["forecast_mw"] - df["actual_mw"]
    df["abs_error"] = df["error"].abs()
    return df


# --------------------------------------------------------------------------- #
# walk-forward: never learn from your own week or later
# --------------------------------------------------------------------------- #
def test_assign_week_is_fixed_seven_day_blocks_from_the_first_target():
    targets = pd.Series(
        [START, START + pd.Timedelta(days=6, hours=23), START + WEEK, START + 3 * WEEK]
    )
    assert list(assign_week(targets)) == [0, 0, 1, 3]


def test_walk_forward_never_uses_errors_from_the_same_or_later_week():
    banded = walk_forward_bands(synthetic_joined())

    non_warmup = banded.loc[banded["band_basis"] != "warm-up"]
    assert len(non_warmup) > 0, "nothing was calibrated walk-forward"

    for _, row in non_warmup.iterrows():
        week_start = START + row["week"] * WEEK
        # the latest target whose error fed this band must predate the row's week
        assert row["band_source_max_target"] < week_start, (
            f"band for {row['startTime']} (week {row['week']}) used an error from "
            f"{row['band_source_max_target']}, which is not strictly earlier"
        )


def test_week_zero_is_flagged_warm_up_and_everything_later_is_not():
    banded = walk_forward_bands(synthetic_joined())
    assert set(banded.loc[banded["week"] == 0, "band_basis"]) == {"warm-up"}
    later = banded.loc[banded["week"] > 0, "band_basis"]
    assert "warm-up" not in set(later)


def test_bands_are_ordered_and_centred_on_the_forecast():
    banded = walk_forward_bands(synthetic_joined())
    row = banded.loc[banded["week"] > 0].iloc[0]
    assert row["p10"] < row["p25"] < row["p50"] < row["p75"] < row["p90"]
    # zero-mean errors -> the median band sits essentially on the forecast
    assert row["p50"] == pytest.approx(row["forecast_mw"], abs=150.0)


def test_low_band_comes_from_the_high_error_quantile():
    """Bias the errors high (over-forecasting) and the plan must drop below it."""
    df = synthetic_joined(sigma=1.0)
    df["actual_mw"] = df["forecast_mw"] - 2000.0  # forecast is always 2000 MW too high
    df["error"] = df["forecast_mw"] - df["actual_mw"]
    df["abs_error"] = df["error"].abs()
    banded = walk_forward_bands(df)
    row = banded.loc[banded["week"] > 0].iloc[0]
    assert row["p50"] == pytest.approx(row["forecast_mw"] - 2000.0, abs=10.0)
    assert row["p10"] < row["forecast_mw"]


# --------------------------------------------------------------------------- #
# calibration
# --------------------------------------------------------------------------- #
def test_calibration_on_normal_errors_is_close_to_nominal():
    banded = walk_forward_bands(synthetic_joined(n_days=28, sigma=500.0, seed=7))
    cal = calibration(banded)

    p10_p90 = cal.loc[cal["interval"] == "P10-P90"].iloc[0]
    p25_p75 = cal.loc[cal["interval"] == "P25-P75"].iloc[0]
    assert p10_p90["nominal_pct"] == 80.0
    assert p25_p75["nominal_pct"] == 50.0
    # stationary synthetic errors: empirical coverage should land near nominal
    assert p10_p90["empirical_pct"] == pytest.approx(80.0, abs=4.0)
    assert p25_p75["empirical_pct"] == pytest.approx(50.0, abs=5.0)
    assert p10_p90["n"] > 400


def test_calibration_excludes_warm_up_rows_by_default():
    banded = walk_forward_bands(synthetic_joined())
    with_warmup = calibration(banded, exclude_warmup=False).iloc[0]["n"]
    without = calibration(banded, exclude_warmup=True).iloc[0]["n"]
    assert without < with_warmup


def test_calibration_reports_a_miscalibrated_band_honestly():
    """Errors that widen sharply after week 0 must show under-coverage."""
    df = synthetic_joined(n_days=28, sigma=100.0, seed=3)
    late = df["startTime"] >= START + WEEK
    df.loc[late, "actual_mw"] = df.loc[late, "forecast_mw"] - np.random.default_rng(
        1
    ).normal(0.0, 2000.0, int(late.sum()))
    df["error"] = df["forecast_mw"] - df["actual_mw"]
    df["abs_error"] = df["error"].abs()

    cal = calibration(walk_forward_bands(df))
    p10_p90 = cal.loc[cal["interval"] == "P10-P90"].iloc[0]
    assert p10_p90["empirical_pct"] < 70.0  # bands built on calm week 0 are too narrow
    assert p10_p90["miss_low_pct"] > 5.0
    assert p10_p90["miss_high_pct"] > 5.0


# --------------------------------------------------------------------------- #
# plan_on and the newsvendor quantile
# --------------------------------------------------------------------------- #
def test_plan_on_higher_confidence_means_a_lower_promise():
    banded = synthetic_joined()
    p50 = plan_on(banded, 0.50)
    p90 = plan_on(banded, 0.90)
    p99 = plan_on(banded, 0.99)
    later = p90["startTime"] >= START + WEEK
    assert p99.loc[later, "plan_mw"].mean() < p90.loc[later, "plan_mw"].mean()
    assert p90.loc[later, "plan_mw"].mean() < p50.loc[later, "plan_mw"].mean()


def test_plan_on_rejects_out_of_range_confidence():
    with pytest.raises(ValueError, match="confidence must be in"):
        plan_on(synthetic_joined(), 1.0)


def test_newsvendor_quantile_values():
    assert newsvendor_quantile(1) == pytest.approx(0.5)
    assert newsvendor_quantile(3) == pytest.approx(0.75)
    assert newsvendor_quantile(9) == pytest.approx(0.9)
    assert newsvendor_quantile(0.5) == pytest.approx(1 / 3)


def test_newsvendor_quantile_rejects_non_positive_ratio():
    with pytest.raises(ValueError, match="cost ratio must be > 0"):
        newsvendor_quantile(0)


def test_cost_ratio_one_plans_on_the_median():
    plan = plan_at_cost_ratio(synthetic_joined(), 1.0)
    assert plan["newsvendor_q"].iloc[0] == pytest.approx(0.5)
    assert plan["wind_quantile"].iloc[0] == pytest.approx(0.5)
    assert plan["shift_vs_median_mw"].abs().max() == pytest.approx(0.0)


def test_higher_shortfall_cost_lowers_the_planned_wind():
    banded = synthetic_joined()
    r1 = plan_at_cost_ratio(banded, 1.0)
    r3 = plan_at_cost_ratio(banded, 3.0)
    assert r3["newsvendor_q"].iloc[0] == pytest.approx(0.75)
    assert r3["wind_quantile"].iloc[0] == pytest.approx(0.25)
    later = r3["startTime"] >= START + WEEK
    assert r3.loc[later, "plan_mw"].mean() < r1.loc[later, "plan_mw"].mean()
    assert r3.loc[later, "shift_vs_median_mw"].mean() < 0


def test_shortfall_summary_tracks_the_cost_asymmetry():
    banded = synthetic_joined()
    cautious = shortfall_summary(plan_at_cost_ratio(banded, 9.0))
    neutral = shortfall_summary(plan_at_cost_ratio(banded, 1.0))
    assert cautious["shortfall_rate_pct"] < neutral["shortfall_rate_pct"]
    assert cautious["mean_headroom_left_on_table_mw"] > neutral["mean_headroom_left_on_table_mw"]
