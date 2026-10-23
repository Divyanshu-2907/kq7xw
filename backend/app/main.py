"""Headroom API. Reads the committed snapshot; never calls Elexon at request time.

Shape of every endpoint: validate and normalise the query into hashable
primitives, hand those to a cached pure-function pipeline, convert to a typed
response. The heavy work (selection + join + walk-forward bands over the whole
month) happens once per distinct parameter set and is then served from memory.

Bands and calibration are always computed over the **whole snapshot**, then
sliced to the requested window. Computing them only inside a narrow window
would leave every row in the warm-up period and quietly change what the numbers
mean depending on how far the user zoomed in.
"""

from __future__ import annotations

import math
import os
from datetime import date, datetime, time, timezone
from functools import lru_cache
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import schemas as s
from .analysis import biggest_misses, data_quality
from .bands import calibration as calc_calibration
from .bands import (
    newsvendor_quantile,
    plan_at_cost_ratio,
    plan_on,
    walk_forward_bands,
)
from .config import (
    DEFAULT_DAY_AHEAD_CUTOFF_LOCAL,
    FORECAST_ALIGNMENT,
    LONDON_TZ,
)
from .data import load_actuals, load_forecasts, load_ingest_report
from .metrics import (
    compute_metrics,
    error_by_horizon,
    error_by_hour_of_day,
    error_by_wind_level,
    join_actuals,
)
from .selection import compute_cutoffs, select_live_forecasts

TARGET_START = pd.Timestamp("2026-01-01T00:00Z")
TARGET_END = pd.Timestamp("2026-02-01T00:00Z")  # exclusive
#: Beyond this, coverage of the month starts dropping (42h holds 100%, 48h is 81%).
MAX_FULL_COVERAGE_HORIZON_H = 42.0
MAX_HORIZON_H = 72.0
DEFAULT_HORIZON_H = 24.0
HORIZON_GRID = [0, 1, 2, 3, 4, 6, 9, 12, 18, 24, 30, 36, 42, 48]

RESOLUTION_NOTE = (
    "FUELHH actuals are half-hourly; WINDFOR forecasts are hourly. The hourly "
    "forecast is held flat across both half-hours of its hour, so every "
    "settlement period is scored. The two halves of an hour therefore share one "
    "forecast value and their errors are correlated: sample sizes overstate "
    "independence."
)
DAY_AHEAD_NOTE = (
    "Default 09:20 Europe/London is the order-book closure of the EPEX SPOT GB "
    "60-minute day-ahead auction. Nord Pool's N2EX hourly GB auction closes at "
    "09:50. In this snapshot the choice is decisive: at 09:20 the freshest "
    "usable publication is the 07:30 one, at 09:50 it is the 09:30 one."
)
ERROR_CONVENTION = "error = forecast - actual, so a positive error means the forecast ran high."
BIAS_CAVEAT = (
    "WINDFOR sits systematically above FUELHH in this snapshot (about +1.6 GW; a "
    "vintage published 14h AFTER delivery is still +1,596 MW high, and a single "
    "scalar removes 47% of MAE). The two datasets appear to cover different wind "
    "populations, so raw bias is not forecast skill."
)

app = FastAPI(
    title="Headroom API",
    version="0.1.0",
    summary="How much wind you can count on before the day-ahead auction closes.",
    description=(
        "National GB wind: Elexon BMRS FUELHH actuals against WINDFOR forecasts, "
        "January 2026.\n\n"
        "**The core rule.** For a target time T and a cutoff C, the live forecast "
        "is the one with the latest `publishTime <= C`. A forecast published after "
        "C is never used for T. Two modes: `horizon` (C = T - H) and `day_ahead` "
        "(C = a clock time on the day before T's London delivery day).\n\n"
        f"**Error convention.** {ERROR_CONVENTION}\n\n"
        f"**Known data caveat.** {BIAS_CAVEAT}\n\n"
        "All generation values are MW. All timestamps are ISO-8601 UTC."
    ),
    openapi_tags=[
        {"name": "meta", "description": "Service and dataset metadata."},
        {"name": "series", "description": "Actual vs live forecast, and its accuracy."},
        {"name": "error analysis", "description": "Where the error comes from."},
        {"name": "planning", "description": "Uncertainty bands and the buying plan."},
        {"name": "explore", "description": "Drill into one delivery day or one period."},
        {"name": "quality", "description": "Coverage, gaps and provenance."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.getenv("HEADROOM_CORS_ORIGINS", "http://localhost:5173").split(",")
        if o.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def _fail(message: str) -> None:
    raise HTTPException(status_code=422, detail=message)


def _window(start: date | None, end: date | None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Validate a start/end date pair against the snapshot's January 2026 scope."""
    lo = TARGET_START if start is None else pd.Timestamp(start, tz="UTC")
    # `end` is inclusive for the caller, half-open internally
    hi = TARGET_END if end is None else pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    window = f"{TARGET_START.date()} to {(TARGET_END - pd.Timedelta(days=1)).date()}"
    if lo < TARGET_START or lo >= TARGET_END:
        _fail(f"start {lo.date()} is outside the snapshot, which covers {window}.")
    if hi <= TARGET_START or hi > TARGET_END:
        _fail(f"end {(hi - pd.Timedelta(days=1)).date()} is outside the snapshot, which covers {window}.")
    if hi <= lo:
        _fail(f"end must be on or after start; got start={lo.date()} end={(hi - pd.Timedelta(days=1)).date()}.")
    return lo, hi


def _mode(mode: str, horizon: float | None, cutoff: str | None) -> tuple[str, float | None, str]:
    """Normalise mode-specific params into hashable primitives."""
    if mode not in ("horizon", "day_ahead"):
        _fail(f"mode must be 'horizon' or 'day_ahead'; got {mode!r}.")
    cutoff_str = cutoff or DEFAULT_DAY_AHEAD_CUTOFF_LOCAL.strftime("%H:%M")
    try:
        time.fromisoformat(cutoff_str)
    except ValueError:
        _fail(f"cutoff must be a 24-hour clock time like '09:20'; got {cutoff_str!r}.")
    if mode == "horizon":
        h = DEFAULT_HORIZON_H if horizon is None else float(horizon)
        if not 0.0 <= h <= MAX_HORIZON_H:
            _fail(f"horizon must be between 0 and {MAX_HORIZON_H:.0f} hours; got {h}.")
        return "horizon", h, cutoff_str
    return "day_ahead", None, cutoff_str


def _day(day: str) -> pd.Timestamp:
    try:
        d = pd.Timestamp(date.fromisoformat(day), tz="UTC")
    except ValueError:
        _fail(f"day must be a date like '2026-01-12'; got {day!r}.")
    if d < TARGET_START or d >= TARGET_END:
        _fail(
            f"day {day} is outside the snapshot, which covers "
            f"{TARGET_START.date()} to {(TARGET_END - pd.Timedelta(days=1)).date()}."
        )
    return d


def _instant(value: str) -> pd.Timestamp:
    try:
        t = pd.Timestamp(value)
    except ValueError:
        _fail(f"time must be an ISO-8601 instant like '2026-01-12T01:00Z'; got {value!r}.")
    t = t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")
    if t < TARGET_START or t >= TARGET_END:
        _fail(f"time {value} is outside the snapshot's January 2026 target window.")
    return t


# --------------------------------------------------------------------------- #
# cached pipeline
# --------------------------------------------------------------------------- #
def _f(x: Any) -> float | None:
    """JSON-safe float: NaN/NaT/None all become null rather than a bogus zero."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def _t(x: Any) -> datetime | None:
    if x is None or x is pd.NaT or (isinstance(x, float) and math.isnan(x)):
        return None
    ts = pd.Timestamp(x)
    return (ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")).to_pydatetime()


@lru_cache(maxsize=64)
def _full_joined(mode: str, horizon_h: float | None, cutoff_str: str) -> pd.DataFrame:
    """Selection + actuals for the whole month, under one parameter set."""
    actuals, forecasts = load_actuals(), load_forecasts()
    selected = select_live_forecasts(
        forecasts,
        actuals["startTime"],
        mode,  # type: ignore[arg-type]
        horizon_h=horizon_h,
        cutoff_local_time=time.fromisoformat(cutoff_str),
    )
    return join_actuals(selected, actuals)


@lru_cache(maxsize=64)
def _full_banded(mode: str, horizon_h: float | None, cutoff_str: str) -> pd.DataFrame:
    """Walk-forward bands over the whole month, so week indices are stable."""
    return walk_forward_bands(_full_joined(mode, horizon_h, cutoff_str))


@lru_cache(maxsize=64)
def _full_plan(
    mode: str, horizon_h: float | None, cutoff_str: str,
    confidence: float | None, cost_ratio: float | None,
) -> pd.DataFrame:
    joined = _full_joined(mode, horizon_h, cutoff_str)
    if cost_ratio is not None:
        return plan_at_cost_ratio(joined, cost_ratio)
    return plan_on(joined, confidence if confidence is not None else 0.9)


@lru_cache(maxsize=16)
def _full_error_by_horizon() -> pd.DataFrame:
    return error_by_horizon(load_forecasts(), load_actuals(), HORIZON_GRID)


def _slice(df: pd.DataFrame, lo: pd.Timestamp, hi: pd.Timestamp) -> pd.DataFrame:
    return df.loc[(df["startTime"] >= lo) & (df["startTime"] < hi)]


def _selection(
    mode: str, horizon_h: float | None, cutoff_str: str,
    lo: pd.Timestamp, hi: pd.Timestamp,
) -> s.Selection:
    return s.Selection(
        mode=mode,  # type: ignore[arg-type]
        horizon_h=horizon_h,
        cutoff_local_time=cutoff_str if mode == "day_ahead" else None,
        alignment=FORECAST_ALIGNMENT,
        start=_t(lo),  # type: ignore[arg-type]
        end=_t(hi),  # type: ignore[arg-type]
    )


def _metrics(df: pd.DataFrame) -> s.Metrics:
    return s.Metrics(**{k: _f(v) if k != "count" else int(v)
                        for k, v in compute_metrics(df).items()})


# --------------------------------------------------------------------------- #
# shared query params
# --------------------------------------------------------------------------- #
StartQ = Query(None, description="First delivery date, inclusive (YYYY-MM-DD). Defaults to 2026-01-01.")
EndQ = Query(None, description="Last delivery date, inclusive (YYYY-MM-DD). Defaults to 2026-01-31.")
ModeQ = Query("horizon", description="`horizon` (cutoff = T - H) or `day_ahead` (cutoff = a clock time the day before).")
HorizonQ = Query(None, ge=0, le=MAX_HORIZON_H, description="Hours before delivery, for `horizon` mode. Defaults to 24.")
CutoffQ = Query(None, description="Day-ahead gate as Europe/London clock time, e.g. `09:20`.")


# --------------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------------- #
@app.get("/api/health", response_model=s.Health, tags=["meta"],
         summary="Liveness and snapshot check")
def health() -> s.Health:
    """Confirm the service is up and the committed snapshot loaded."""
    return s.Health(
        status="ok",
        snapshot_loaded=True,
        actual_rows=len(load_actuals()),
        forecast_rows=len(load_forecasts()),
    )


@app.get("/api/meta", response_model=s.Meta, tags=["meta"],
         summary="Dataset range, horizon limits and conventions")
def meta() -> s.Meta:
    """What the UI needs to configure itself: the date range the snapshot covers,
    the horizon range the data actually supports, the default day-ahead gate, and
    the resolution caveat behind every number."""
    forecasts = load_forecasts()
    lead = (forecasts["startTime"] - forecasts["publishTime"]).dt.total_seconds() / 3600
    pubs = sorted(forecasts["publishTime"].dt.strftime("%H:%M").unique())
    return s.Meta(
        target_start=_t(TARGET_START),  # type: ignore[arg-type]
        target_end=_t(TARGET_END),  # type: ignore[arg-type]
        horizon=s.HorizonRange(
            min_h=0.0,
            max_h=MAX_FULL_COVERAGE_HORIZON_H,
            max_lead_in_data_h=float(lead.max()),
        ),
        default_day_ahead_cutoff_local=DEFAULT_DAY_AHEAD_CUTOFF_LOCAL.strftime("%H:%M"),
        day_ahead_cutoff_note=DAY_AHEAD_NOTE,
        actual_resolution="PT30M",
        forecast_resolution="PT1H",
        alignment=FORECAST_ALIGNMENT,
        resolution_note=RESOLUTION_NOTE,
        publish_times_utc=pubs,
        error_convention=ERROR_CONVENTION,
    )


@app.get("/api/series", response_model=s.SeriesResponse, tags=["series"],
         summary="Actual vs live forecast, with uncertainty bands")
def series(
    start: date | None = StartQ, end: date | None = EndQ, mode: str = ModeQ,
    horizon: float | None = HorizonQ, cutoff: str | None = CutoffQ,
) -> s.SeriesResponse:
    """Per delivery period: the actual, the forecast that was live at the cutoff,
    its lead time, and the walk-forward P10-P90 band around it.

    Periods with no eligible forecast are returned with nulls and a `reason`
    rather than omitted, so a gap in the chart is visible as a gap."""
    lo, hi = _window(start, end)
    m, h, c = _mode(mode, horizon, cutoff)
    banded = _slice(_full_banded(m, h, c), lo, hi)
    return s.SeriesResponse(
        selection=_selection(m, h, c, lo, hi),
        metrics=_metrics(banded),
        points=[
            s.SeriesPoint(
                start_time=_t(r.startTime), cutoff=_t(r.cutoff),
                publish_time=_t(r.publishTime), lead_h=_f(r.lead_h),
                forecast_mw=_f(r.forecast_mw), actual_mw=_f(r.actual_mw),
                error_mw=_f(r.error), p10_mw=_f(r.p10), p25_mw=_f(r.p25),
                p50_mw=_f(r.p50), p75_mw=_f(r.p75), p90_mw=_f(r.p90),
                band_basis=r.band_basis if isinstance(r.band_basis, str) else None,
                reason=r.reason,
            )
            for r in banded.itertuples()
        ],
    )


@app.get("/api/metrics", response_model=s.MetricsResponse, tags=["series"],
         summary="Headline accuracy for a window")
def metrics_endpoint(
    start: date | None = StartQ, end: date | None = EndQ, mode: str = ModeQ,
    horizon: float | None = HorizonQ, cutoff: str | None = CutoffQ,
) -> s.MetricsResponse:
    """MAE, RMSE, bias, nMAE and P50/P90 absolute error over the selected window.

    nMAE normalises by mean actual generation rather than per-period actual:
    MAPE would explode on the many half-hours when wind output is near zero."""
    lo, hi = _window(start, end)
    m, h, c = _mode(mode, horizon, cutoff)
    return s.MetricsResponse(
        selection=_selection(m, h, c, lo, hi),
        metrics=_metrics(_slice(_full_joined(m, h, c), lo, hi)),
    )


@app.get("/api/error-by-horizon", response_model=s.ErrorByHorizonResponse,
         tags=["error analysis"], summary="The value of waiting")
def error_by_horizon_endpoint() -> s.ErrorByHorizonResponse:
    """Accuracy at each horizon, every row from its own independent no-lookahead
    selection over the whole month.

    Watch `coverage_pct`: beyond about 42 hours fewer target periods have any
    eligible forecast, so part of the apparent degradation is thinning coverage."""
    rows = _full_error_by_horizon()
    return s.ErrorByHorizonResponse(
        rows=[
            s.HorizonRow(**{k: (int(v) if k == "count" else _f(v)) for k, v in r.items()})
            for r in rows.to_dict(orient="records")
        ],
        note="Each horizon is an independent selection; rows are not a time series.",
    )


@app.get("/api/error-by-hour", response_model=s.ErrorByHourResponse,
         tags=["error analysis"], summary="Error by hour of the delivery day")
def error_by_hour_endpoint(
    start: date | None = StartQ, end: date | None = EndQ, mode: str = ModeQ,
    horizon: float | None = HorizonQ, cutoff: str | None = CutoffQ,
) -> s.ErrorByHourResponse:
    """Accuracy grouped by local (Europe/London) hour of the delivery period."""
    lo, hi = _window(start, end)
    m, h, c = _mode(mode, horizon, cutoff)
    rows = error_by_hour_of_day(_slice(_full_joined(m, h, c), lo, hi))
    return s.ErrorByHourResponse(
        selection=_selection(m, h, c, lo, hi),
        rows=[
            s.HourRow(**{k: (int(v) if k in ("count", "hour") else _f(v))
                         for k, v in r.items()})
            for r in rows.to_dict(orient="records")
        ],
    )


@app.get("/api/error-by-level", response_model=s.ErrorByLevelResponse,
         tags=["error analysis"], summary="Error by forecast wind level")
def error_by_level_endpoint(
    start: date | None = StartQ, end: date | None = EndQ, mode: str = ModeQ,
    horizon: float | None = HorizonQ, cutoff: str | None = CutoffQ,
) -> s.ErrorByLevelResponse:
    """Accuracy bucketed by forecast MW.

    Bucketed by forecast rather than actual on purpose: at decision time the
    forecast is all the desk has, so "how wrong is a 12 GW forecast" is a
    question that can actually inform a buy."""
    lo, hi = _window(start, end)
    m, h, c = _mode(mode, horizon, cutoff)
    rows = error_by_wind_level(_slice(_full_joined(m, h, c), lo, hi))
    return s.ErrorByLevelResponse(
        selection=_selection(m, h, c, lo, hi),
        rows=[
            s.LevelRow(**{k: (int(v) if k == "count" else v if k == "wind_level" else _f(v))
                          for k, v in r.items()})
            for r in rows.to_dict(orient="records")
        ],
        note="Buckets are left-closed MW ranges of the live forecast.",
    )


@app.get("/api/calibration", response_model=s.CalibrationResponse, tags=["planning"],
         summary="Did the bands do what they promised?")
def calibration_endpoint(
    start: date | None = StartQ, end: date | None = EndQ, mode: str = ModeQ,
    horizon: float | None = HorizonQ, cutoff: str | None = CutoffQ,
) -> s.CalibrationResponse:
    """Empirical coverage of each nominal band, reported as measured.

    The first week is excluded: with no earlier errors to learn from, its bands
    borrow from the whole sample and would flatter the result."""
    lo, hi = _window(start, end)
    m, h, c = _mode(mode, horizon, cutoff)
    rows = calc_calibration(_slice(_full_banded(m, h, c), lo, hi))
    return s.CalibrationResponse(
        selection=_selection(m, h, c, lo, hi),
        rows=[
            s.CalibrationRow(**{k: (int(v) if k == "n" else v if k == "interval" else _f(v))
                                for k, v in r.items()})
            for r in rows.to_dict(orient="records")
        ],
        warmup_excluded=True,
        note="Bands are calibrated walk-forward: week k uses errors from weeks < k only.",
    )


@app.get("/api/plan", response_model=s.PlanResponse, tags=["planning"],
         summary="Plan on X MW, optionally cost-aware")
def plan(
    start: date | None = StartQ, end: date | None = EndQ,
    confidence: float | None = Query(None, gt=0, lt=1, description="e.g. 0.9 for 'wind should be at least this, 90% of the time'."),
    cost_ratio: float | None = Query(None, gt=0, description="How much worse a shortfall is than a surplus, per MW. Overrides `confidence`."),
    mode: str = ModeQ, horizon: float | None = HorizonQ, cutoff: str | None = CutoffQ,
) -> s.PlanResponse:
    """The MW of wind you can count on, per period, plus how the plan would have fared.

    Give `confidence` for a straight quantile, or `cost_ratio` (r) to price a
    shortfall as worse than a surplus: the plan then sits at the newsvendor
    quantile q = r/(1+r) of demand to cover, which is the 1-q quantile of wind.
    The more you fear being short, the lower the wind figure you plan on."""
    lo, hi = _window(start, end)
    m, h, c = _mode(mode, horizon, cutoff)
    if confidence is not None and cost_ratio is not None:
        _fail("give either confidence or cost_ratio, not both.")
    df = _slice(_full_plan(m, h, c, confidence, cost_ratio), lo, hi)
    usable = df.loc[df["plan_mw"].notna() & df["actual_mw"].notna()]
    gap = usable["actual_mw"] - usable["plan_mw"]
    short = gap < 0
    q = newsvendor_quantile(cost_ratio) if cost_ratio is not None else None
    return s.PlanResponse(
        selection=_selection(m, h, c, lo, hi),
        confidence=confidence if cost_ratio is None else None,
        cost_ratio=cost_ratio,
        newsvendor_q=q,
        wind_quantile=(1.0 - q) if q is not None else None,
        totals=s.PlanTotals(
            periods=int(len(usable)),
            mean_forecast_mw=_f(usable["forecast_mw"].mean()),
            mean_plan_mw=_f(usable["plan_mw"].mean()),
            mean_actual_mw=_f(usable["actual_mw"].mean()),
            plan_vs_forecast_mw=_f((usable["plan_mw"] - usable["forecast_mw"]).mean()),
            shortfall_rate_pct=_f(100.0 * short.mean()) if len(usable) else None,
            mean_shortfall_mw=_f(-gap[short].mean()) if short.any() else 0.0,
            worst_shortfall_mw=_f(-gap.min()) if short.any() else 0.0,
            mean_headroom_left_on_table_mw=_f(gap.mean()),
        ),
        points=[
            s.PlanPoint(
                start_time=_t(r.startTime), lead_h=_f(r.lead_h),
                forecast_mw=_f(r.forecast_mw), actual_mw=_f(r.actual_mw),
                plan_mw=_f(r.plan_mw),
                median_plan_mw=_f(getattr(r, "median_plan_mw", None)),
                shift_vs_median_mw=_f(getattr(r, "shift_vs_median_mw", None)),
                band_basis=r.band_basis if isinstance(r.band_basis, str) else None,
            )
            for r in df.itertuples()
        ],
    )


@app.get("/api/replay", response_model=s.ReplayResponse, tags=["explore"],
         summary="Decision Replay: one delivery day, every vintage")
def replay(
    day: str = Query(..., description="Delivery day, YYYY-MM-DD."),
    cutoff: str | None = CutoffQ,
) -> s.ReplayResponse:
    """Every forecast vintage published for one delivery day, oldest first.

    Drive a publish-time slider from `publish_times`: vintages at or before the
    slider were available, later ones were not. `cutoff` is the day-ahead gate,
    and the actual should stay hidden until the slider passes delivery."""
    d = _day(day)
    _, _, c = _mode("day_ahead", None, cutoff)
    day_end = d + pd.Timedelta(days=1)
    forecasts, actuals = load_forecasts(), load_actuals()

    fc = forecasts.loc[(forecasts["startTime"] >= d) & (forecasts["startTime"] < day_end)]
    act = actuals.loc[(actuals["startTime"] >= d) & (actuals["startTime"] < day_end)]
    gate = compute_cutoffs([d], "day_ahead", cutoff_local_time=time.fromisoformat(c))[0]

    pubs = sorted(fc["publishTime"].unique())
    eligible = [p for p in pubs if p <= gate]
    live_pub = max(eligible) if eligible else None

    return s.ReplayResponse(
        day=day,
        delivery_start=_t(d),  # type: ignore[arg-type]
        delivery_end=_t(day_end),  # type: ignore[arg-type]
        cutoff=_t(gate),  # type: ignore[arg-type]
        cutoff_local_time=c,
        publish_times=[_t(p) for p in pubs],  # type: ignore[list-item]
        vintages=[
            s.Vintage(
                publish_time=_t(p),  # type: ignore[arg-type]
                eligible_at_cutoff=bool(p <= gate),
                is_live=bool(live_pub is not None and p == live_pub),
                points=[
                    s.VintagePoint(start_time=_t(r.startTime), forecast_mw=_f(r.generation))  # type: ignore[arg-type]
                    for r in fc.loc[fc["publishTime"] == p]
                    .sort_values("startTime")
                    .itertuples()
                ],
            )
            for p in pubs
        ],
        actuals=[
            s.ActualPoint(start_time=_t(r.startTime), actual_mw=_f(r.generation))  # type: ignore[arg-type]
            for r in act.sort_values("startTime").itertuples()
        ],
    )


@app.get("/api/slot", response_model=s.SlotResponse, tags=["explore"],
         summary="Historical explorer: one target period's full forecast history")
def slot(
    time_: str = Query(..., alias="time", description="Target period start, ISO-8601, e.g. `2026-01-12T01:00Z`."),
    mode: str = ModeQ, horizon: float | None = HorizonQ, cutoff: str | None = CutoffQ,
) -> s.SlotResponse:
    """Every forecast ever published for one delivery period: publish time, lead
    time, MW, whether it was eligible at the cutoff, and which one was live.

    The hourly forecast covers both half-hours of its hour, so a `:30` target
    resolves to its parent hour's vintages."""
    t = _instant(time_)
    m, h, c = _mode(mode, horizon, cutoff)
    joined = _full_joined(m, h, c)
    row = joined.loc[joined["startTime"] == t]
    if row.empty:
        _fail(f"no delivery period starts at {t.isoformat()}; actuals are half-hourly.")
    row = row.iloc[0]

    forecasts = load_forecasts()
    key = t.floor("h") if FORECAST_ALIGNMENT == "hold" else t
    hist = forecasts.loc[forecasts["startTime"] == key].sort_values("publishTime")
    gate = pd.Timestamp(row["cutoff"])
    live_pub = row["publishTime"] if pd.notna(row["publishTime"]) else None

    return s.SlotResponse(
        start_time=_t(t),  # type: ignore[arg-type]
        cutoff=_t(gate),  # type: ignore[arg-type]
        selection=_selection(m, h, c, t, t + pd.Timedelta(minutes=30)),
        actual_mw=_f(row["actual_mw"]),
        live_forecast_mw=_f(row["forecast_mw"]),
        live_publish_time=_t(live_pub),
        error_mw=_f(row["error"]),
        forecasts=[
            s.SlotForecast(
                publish_time=_t(r.publishTime),  # type: ignore[arg-type]
                lead_h=_f((t - r.publishTime).total_seconds() / 3600),  # type: ignore[arg-type]
                forecast_mw=_f(r.generation),  # type: ignore[arg-type]
                eligible_at_cutoff=bool(r.publishTime <= gate),
                is_live=bool(live_pub is not None and r.publishTime == live_pub),
            )
            for r in hist.itertuples()
        ],
    )


@app.get("/api/misses", response_model=s.MissesResponse, tags=["error analysis"],
         summary="Biggest misses, split timing vs size")
def misses(
    n: int = Query(10, ge=1, le=100, description="How many periods to return."),
    start: date | None = StartQ, end: date | None = EndQ, mode: str = ModeQ,
    horizon: float | None = HorizonQ, cutoff: str | None = CutoffQ,
) -> s.MissesResponse:
    """The worst periods by absolute error, each decomposed timing vs size.

    The forecast curve is shifted -3..+3 hours and scored on the same periods
    each time. If the best shift removes at least half the local error the miss
    was about *when* the wind arrived; otherwise it was about *how much*.

    Expect clusters: a bad day produces many consecutive bad half-hours, so the
    list can be dominated by one date."""
    lo, hi = _window(start, end)
    m, h, c = _mode(mode, horizon, cutoff)
    rows = biggest_misses(_slice(_full_joined(m, h, c), lo, hi), n=n)
    return s.MissesResponse(
        selection=_selection(m, h, c, lo, hi),
        rows=[
            s.Miss(
                rank=i + 1,
                start_time=_t(r["startTime"]),  # type: ignore[arg-type]
                publish_time=_t(r["publishTime"]),
                lead_h=_f(r["lead_h"]),
                forecast_mw=_f(r["forecast_mw"]),  # type: ignore[arg-type]
                actual_mw=_f(r["actual_mw"]),  # type: ignore[arg-type]
                error_mw=_f(r["error"]),  # type: ignore[arg-type]
                abs_error_mw=_f(r["abs_error"]),  # type: ignore[arg-type]
                miss_type=r["miss_type"],
                best_shift_h=_f(r["best_shift_h"]),
                window_mae_unshifted_mw=_f(r["window_mae_unshifted_mw"]),
                window_mae_at_best_shift_mw=_f(r["window_mae_at_best_shift_mw"]),
                error_removed_by_shift_pct=_f(r["error_removed_by_shift_pct"]),
                shift_curve_mw={f"{k:+.0f}": v for k, v in (r["shift_curve_mw"] or {}).items()},
                decomposition_note=r["decomposition_note"],
            )
            for i, r in enumerate(rows.to_dict(orient="records"))
        ],
        note="Click a row through to /api/replay for its delivery day.",
    )


@app.get("/api/data-quality", response_model=s.DataQualityResponse, tags=["quality"],
         summary="Coverage, gaps, duplicates and how each was handled")
def data_quality_endpoint() -> s.DataQualityResponse:
    """Live checks over the committed snapshot, plus the ingest record it came with.

    Both are reported so a discrepancy between what the fetch saw and what the
    snapshot contains is visible rather than hidden."""
    dq = data_quality(load_ingest_report(), load_actuals(), load_forecasts())
    live = dq["live_checks"]
    return s.DataQualityResponse(
        **{k: v for k, v in live.items()},
        coverage_per_day=[s.CoverageDay(**d) for d in dq["coverage_per_day"]],
        handling=dq["handling"],
        ingest=dq["ingest_report"],
    )
