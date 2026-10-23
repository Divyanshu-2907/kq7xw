"""Snapshot loader contract: tz-aware UTC, no duplicate keys."""

from __future__ import annotations

import pandas as pd

from app.data import load_actuals, load_forecasts, load_ingest_report


def test_loader_returns_tz_aware_utc_columns():
    actuals = load_actuals()
    forecasts = load_forecasts()

    assert str(actuals["startTime"].dt.tz) == "UTC"
    assert str(forecasts["startTime"].dt.tz) == "UTC"
    assert str(forecasts["publishTime"].dt.tz) == "UTC"
    assert actuals["generation"].dtype == "float64"
    assert forecasts["generation"].dtype == "float64"


def test_no_duplicate_keys():
    assert not load_actuals()["startTime"].duplicated().any()
    assert (
        not load_forecasts().duplicated(subset=["startTime", "publishTime"]).any()
    )


def test_snapshot_matches_ingest_report():
    report = load_ingest_report()
    assert len(load_actuals()) == report["actual_rows"]
    assert len(load_forecasts()) == report["forecast_rows"]


def test_snapshot_is_sorted_and_within_the_target_month():
    actuals, forecasts = load_actuals(), load_forecasts()
    assert actuals["startTime"].is_monotonic_increasing
    lo, hi = pd.Timestamp("2026-01-01T00:00Z"), pd.Timestamp("2026-02-01T00:00Z")
    for df in (actuals, forecasts):
        assert df["startTime"].min() >= lo
        assert df["startTime"].max() < hi
