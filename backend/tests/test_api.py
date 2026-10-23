"""TestClient coverage for every endpoint: status, shape, one known value.

Known values are pinned against the committed January 2026 snapshot, so a
change in the selection rule or the snapshot breaks these tests loudly.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# The worst miss in the month, used as a fixed point throughout.
WORST = "2026-01-12T01:00Z"


def get(url: str, expect: int = 200):
    r = client.get(url)
    assert r.status_code == expect, f"{url} -> {r.status_code}: {r.text[:300]}"
    return r.json()


# --------------------------------------------------------------------------- #
# meta
# --------------------------------------------------------------------------- #
def test_health():
    body = get("/api/health")
    assert body["status"] == "ok"
    assert body["snapshot_loaded"] is True
    assert body["actual_rows"] == 1488
    assert body["forecast_rows"] == 18080


def test_meta_reports_the_real_range_and_limits():
    body = get("/api/meta")
    assert body["target_start"] == "2026-01-01T00:00:00Z"
    assert body["target_end"] == "2026-02-01T00:00:00Z"
    assert body["horizon"]["max_lead_in_data_h"] == 66.5
    assert body["horizon"]["max_h"] == 42.0
    assert body["default_day_ahead_cutoff_local"] == "09:20"
    assert body["actual_resolution"] == "PT30M"
    assert body["forecast_resolution"] == "PT1H"
    assert body["alignment"] == "hold"
    assert "09:30" in body["publish_times_utc"]
    assert "MAPE" not in body["error_convention"]


def test_openapi_documents_every_endpoint_with_a_description():
    spec = get("/openapi.json")
    paths = spec["paths"]
    expected = {
        "/api/health", "/api/meta", "/api/series", "/api/metrics",
        "/api/error-by-horizon", "/api/error-by-hour", "/api/error-by-level",
        "/api/calibration", "/api/plan", "/api/replay", "/api/slot",
        "/api/misses", "/api/data-quality",
    }
    assert expected <= set(paths)
    for path in expected:
        op = paths[path]["get"]
        assert op.get("summary"), f"{path} has no summary"
        assert op.get("description"), f"{path} has no description"
        assert op.get("tags"), f"{path} has no tag"


# --------------------------------------------------------------------------- #
# series / metrics
# --------------------------------------------------------------------------- #
def test_series_shape_and_known_values():
    body = get("/api/series?start=2026-01-12&end=2026-01-12&mode=day_ahead")
    assert len(body["points"]) == 48  # half-hourly, one full day
    first = body["points"][0]
    assert first["start_time"] == "2026-01-12T00:00:00Z"
    assert first["forecast_mw"] == 20790.0
    assert first["actual_mw"] == 13954.0
    assert first["error_mw"] == pytest.approx(6836.0)
    assert first["reason"] == "ok"
    assert first["p10_mw"] < first["p50_mw"] < first["p90_mw"]
    assert body["selection"]["mode"] == "day_ahead"
    assert body["selection"]["cutoff_local_time"] == "09:20"
    assert body["metrics"]["count"] == 48


def test_series_timestamps_are_iso_utc_with_a_z():
    body = get("/api/series?start=2026-01-05&end=2026-01-05")
    for point in body["points"][:5]:
        assert point["start_time"].endswith("Z")
        assert point["cutoff"].endswith("Z")


def test_series_defaults_to_the_whole_month():
    body = get("/api/series")
    assert len(body["points"]) == 1488


def test_metrics_matches_the_day_ahead_findings():
    body = get("/api/metrics?mode=day_ahead&cutoff=09:20")
    m = body["metrics"]
    assert m["count"] == 1488
    assert m["coverage_pct"] == 100.0
    assert m["mae_mw"] == pytest.approx(2145.2, abs=0.1)
    assert m["rmse_mw"] == pytest.approx(2615.8, abs=0.1)
    assert m["bias_mw"] == pytest.approx(1851.9, abs=0.1)  # positive = over-forecast
    assert m["nmae_pct"] == pytest.approx(18.52, abs=0.01)


def test_later_gate_uses_a_fresher_vintage():
    """The ten minutes between the EPEX and N2EX gates change the answer."""
    early = get("/api/metrics?mode=day_ahead&cutoff=09:20")["metrics"]
    late = get("/api/metrics?mode=day_ahead&cutoff=09:50")["metrics"]
    assert late["mae_mw"] < early["mae_mw"]
    assert late["mae_mw"] == pytest.approx(2126.1, abs=0.1)


def test_horizon_mode_degrades_with_distance():
    near = get("/api/metrics?mode=horizon&horizon=0")["metrics"]
    far = get("/api/metrics?mode=horizon&horizon=42")["metrics"]
    assert near["mae_mw"] == pytest.approx(1797.8, abs=0.1)
    assert far["mae_mw"] == pytest.approx(2318.6, abs=0.1)


# --------------------------------------------------------------------------- #
# error breakdowns
# --------------------------------------------------------------------------- #
def test_error_by_horizon_covers_the_grid_and_flags_thinning_coverage():
    body = get("/api/error-by-horizon")
    rows = {r["horizon_h"]: r for r in body["rows"]}
    assert set(rows) == {0, 1, 2, 3, 4, 6, 9, 12, 18, 24, 30, 36, 42, 48}
    assert rows[0]["coverage_pct"] == 100.0
    assert rows[48]["coverage_pct"] == pytest.approx(81.25, abs=0.01)
    assert rows[0]["mae_mw"] < rows[42]["mae_mw"]  # waiting pays
    assert body["note"]


def test_error_by_hour_has_24_rows_and_a_diurnal_pattern():
    body = get("/api/error-by-hour?mode=horizon&horizon=24")
    rows = body["rows"]
    assert len(rows) == 24
    assert [r["hour"] for r in rows] == list(range(24))
    assert sum(r["count"] for r in rows) == 1488
    by_hour = {r["hour"]: r["mae_mw"] for r in rows}
    assert by_hour[5] == pytest.approx(2533.1, abs=0.1)  # worst, overnight
    assert by_hour[15] == pytest.approx(1659.9, abs=0.1)  # best, afternoon
    assert by_hour[5] > by_hour[15]


def test_error_by_level_buckets_on_the_forecast():
    body = get("/api/error-by-level?mode=horizon&horizon=24")
    rows = body["rows"]
    assert sum(r["count"] for r in rows) == 1488
    empty = [r for r in rows if r["count"] == 0]
    assert empty and empty[0]["mae_mw"] is None  # 0-2 GW never forecast; null not 0
    biggest = max(rows, key=lambda r: r["count"])
    assert biggest["count"] == 715
    assert biggest["mae_mw"] == pytest.approx(2740.0, abs=0.1)


# --------------------------------------------------------------------------- #
# planning
# --------------------------------------------------------------------------- #
def test_calibration_reports_measured_coverage():
    body = get("/api/calibration?mode=horizon&horizon=24")
    rows = {r["interval"]: r for r in body["rows"]}
    assert set(rows) == {"P10-P90", "P25-P75"}
    assert rows["P10-P90"]["nominal_pct"] == 80.0
    assert rows["P10-P90"]["empirical_pct"] == pytest.approx(83.1, abs=0.1)
    assert rows["P10-P90"]["n"] == 1152  # week 0 excluded
    assert body["warmup_excluded"] is True


def test_plan_on_confidence_shape_and_direction():
    body = get("/api/plan?confidence=0.9&mode=horizon&horizon=24")
    assert body["confidence"] == 0.9
    assert body["cost_ratio"] is None
    assert len(body["points"]) == 1488
    totals = body["totals"]
    assert totals["mean_plan_mw"] < totals["mean_forecast_mw"]
    assert totals["plan_vs_forecast_mw"] < 0
    assert 0.0 <= totals["shortfall_rate_pct"] <= 100.0


def test_plan_cost_ratio_uses_the_newsvendor_quantile():
    body = get("/api/plan?cost_ratio=3&mode=horizon&horizon=24")
    assert body["newsvendor_q"] == pytest.approx(0.75)
    assert body["wind_quantile"] == pytest.approx(0.25)
    assert body["confidence"] is None
    assert body["totals"]["mean_plan_mw"] < body["totals"]["mean_forecast_mw"]


def test_higher_cost_ratio_plans_lower_and_runs_short_less_often():
    cheap = get("/api/plan?cost_ratio=1&mode=horizon&horizon=24")["totals"]
    dear = get("/api/plan?cost_ratio=5&mode=horizon&horizon=24")["totals"]
    assert dear["mean_plan_mw"] < cheap["mean_plan_mw"]
    assert dear["shortfall_rate_pct"] < cheap["shortfall_rate_pct"]


# --------------------------------------------------------------------------- #
# explore
# --------------------------------------------------------------------------- #
def test_replay_returns_every_vintage_with_one_live_and_a_cutoff():
    body = get("/api/replay?day=2026-01-12")
    assert body["day"] == "2026-01-12"
    assert body["cutoff"] == "2026-01-11T09:20:00Z"
    assert body["cutoff_local_time"] == "09:20"
    assert len(body["vintages"]) == 32
    assert len(body["publish_times"]) == 32
    assert body["publish_times"] == sorted(body["publish_times"])  # slider order
    assert sum(v["is_live"] for v in body["vintages"]) == 1
    assert sum(v["eligible_at_cutoff"] for v in body["vintages"]) == 11
    live = next(v for v in body["vintages"] if v["is_live"])
    assert live["publish_time"] == "2026-01-11T07:30:00Z"
    assert len(body["actuals"]) == 48
    # nothing published after the cutoff may be marked eligible
    for v in body["vintages"]:
        assert v["eligible_at_cutoff"] == (v["publish_time"] <= body["cutoff"])


def test_slot_shows_full_vintage_history_and_marks_the_live_one():
    body = get(f"/api/slot?time={WORST}&mode=day_ahead")
    assert body["start_time"] == "2026-01-12T01:00:00Z"
    assert body["cutoff"] == "2026-01-11T09:20:00Z"
    assert body["actual_mw"] == 14048.0
    assert body["live_forecast_mw"] == 20942.0
    assert body["live_publish_time"] == "2026-01-11T07:30:00Z"
    assert body["error_mw"] == pytest.approx(6894.0)
    assert len(body["forecasts"]) == 24
    assert sum(f["is_live"] for f in body["forecasts"]) == 1
    assert sum(f["eligible_at_cutoff"] for f in body["forecasts"]) == 11
    # the live one is the latest eligible one
    eligible = [f for f in body["forecasts"] if f["eligible_at_cutoff"]]
    assert max(eligible, key=lambda f: f["publish_time"])["is_live"] is True
    # leads shrink as publication approaches delivery
    leads = [f["lead_h"] for f in body["forecasts"]]
    assert leads == sorted(leads, reverse=True)


def test_slot_resolves_a_half_hour_target_to_its_parent_hour():
    on_hour = get(f"/api/slot?time={WORST}")
    half_past = get("/api/slot?time=2026-01-12T01:30Z")
    assert half_past["live_forecast_mw"] == on_hour["live_forecast_mw"]
    assert half_past["actual_mw"] != on_hour["actual_mw"]  # actuals are half-hourly


# --------------------------------------------------------------------------- #
# misses / quality
# --------------------------------------------------------------------------- #
def test_misses_ranks_and_decomposes():
    body = get("/api/misses?n=3&mode=day_ahead")
    rows = body["rows"]
    assert [r["rank"] for r in rows] == [1, 2, 3]
    worst = rows[0]
    assert worst["start_time"] == "2026-01-12T01:00:00Z"
    assert worst["forecast_mw"] == 20942.0
    assert worst["actual_mw"] == 14048.0
    assert worst["abs_error_mw"] == pytest.approx(6894.0)
    assert worst["miss_type"] == "size"
    assert len(worst["shift_curve_mw"]) == 7
    assert [r["abs_error_mw"] for r in rows] == sorted(
        [r["abs_error_mw"] for r in rows], reverse=True
    )


def test_misses_respects_n():
    assert len(get("/api/misses?n=1")["rows"]) == 1
    assert len(get("/api/misses?n=25")["rows"]) == 25


def test_data_quality_reports_a_clean_snapshot_and_the_one_anomaly():
    body = get("/api/data-quality")
    assert body["actual_rows"] == 1488
    assert body["actual_periods_expected"] == 1488
    assert body["actual_coverage_pct"] == 100.0
    assert body["actual_periods_missing"] == []
    assert body["actual_duplicate_start_times"] == 0
    assert body["forecast_duplicate_keys"] == 0
    assert body["forecast_lead_h_max"] == 66.5
    assert body["forecast_lead_h_min"] == -25.5
    assert body["forecast_negative_lead_rows"] == 3697
    assert len(body["coverage_per_day"]) == 31
    assert all(d["coverage_pct"] == 100.0 for d in body["coverage_per_day"])
    # the one off-schedule publication in the month
    assert body["publish_clock_times"]["12:25"] == 1
    assert body["publish_clock_times"]["11:30"] == 32
    assert "duplicates" in body["handling"]
    assert body["ingest"]["actual_rows"] == 1488


# --------------------------------------------------------------------------- #
# validation: clear 422s
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "url,fragment",
    [
        ("/api/series?start=2025-12-15", "outside the snapshot"),
        ("/api/series?end=2026-02-10", "outside the snapshot"),
        ("/api/series?start=2026-01-20&end=2026-01-10", "on or after start"),
        ("/api/series?mode=magic", "must be 'horizon' or 'day_ahead'"),
        ("/api/series?cutoff=9am", "24-hour clock time"),
        ("/api/replay?day=2026-03-01", "outside the snapshot"),
        ("/api/replay?day=nonsense", "must be a date"),
        ("/api/slot?time=2026-01-12T01:07Z", "half-hourly"),
        ("/api/slot?time=2025-06-01T00:00Z", "outside the snapshot"),
        ("/api/plan?confidence=0.9&cost_ratio=3", "not both"),
    ],
)
def test_bad_input_gives_a_clear_422(url, fragment):
    body = client.get(url)
    assert body.status_code == 422, f"{url} -> {body.status_code}"
    assert fragment in body.json()["detail"]


@pytest.mark.parametrize(
    "url",
    [
        "/api/series?horizon=500",
        "/api/series?horizon=-1",
        "/api/plan?confidence=1.5",
        "/api/plan?cost_ratio=0",
        "/api/misses?n=0",
        "/api/misses?n=1000",
        "/api/series?start=not-a-date",
    ],
)
def test_out_of_range_params_are_rejected_by_the_schema(url):
    assert client.get(url).status_code == 422


def test_january_boundaries_are_accepted():
    body = get("/api/series?start=2026-01-01&end=2026-01-31")
    assert len(body["points"]) == 1488


# --------------------------------------------------------------------------- #
# caching
# --------------------------------------------------------------------------- #
def test_repeated_heavy_requests_are_served_from_cache():
    from app.main import _full_banded

    _full_banded.cache_clear()
    get("/api/series?mode=horizon&horizon=24")
    after_first = _full_banded.cache_info()
    get("/api/series?mode=horizon&horizon=24")
    after_second = _full_banded.cache_info()
    assert after_second.hits > after_first.hits
    assert after_second.misses == after_first.misses
