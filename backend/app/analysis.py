"""Worst-case analysis and data quality. Pure functions, no FastAPI, no I/O.

The headline question for the desk is not "what is the average error" but "what
happened on the days it went wrong, and was the forecast wrong about *when* the
wind arrived or about *how much*". A timing miss is a different operational
problem from a level miss: timing errors partly self-cancel across a day and
hint at using a wider delivery window, level errors do not.
"""

from __future__ import annotations


import pandas as pd

#: Shifts tried when testing whether a miss is a timing miss, in hours.
DEFAULT_SHIFTS_H: tuple[float, ...] = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0)
#: Half-width of the local window the shifted forecast is scored over.
DEFAULT_WINDOW_H: float = 3.0
#: Fraction of the local error a shift must remove to call the miss "timing".
TIMING_THRESHOLD: float = 0.5


def biggest_misses(
    joined: pd.DataFrame,
    n: int = 10,
    shifts_h: tuple[float, ...] = DEFAULT_SHIFTS_H,
    window_h: float = DEFAULT_WINDOW_H,
    timing_threshold: float = TIMING_THRESHOLD,
) -> pd.DataFrame:
    """The ``n`` worst periods by absolute error, each decomposed timing vs size.

    Returns one row per miss with ``startTime``, ``forecast_mw``, ``actual_mw``,
    ``error``, ``abs_error``, ``lead_h``, plus the decomposition fields from
    :func:`decompose_timing_vs_size`.
    """
    scored = joined.loc[joined["error"].notna()]
    worst = scored.nlargest(n, "abs_error")
    rows = []
    for _, miss in worst.iterrows():
        d = decompose_timing_vs_size(
            joined,
            miss["startTime"],
            shifts_h=shifts_h,
            window_h=window_h,
            timing_threshold=timing_threshold,
        )
        rows.append(
            {
                "startTime": miss["startTime"],
                "forecast_mw": float(miss["forecast_mw"]),
                "actual_mw": float(miss["actual_mw"]),
                "error": float(miss["error"]),
                "abs_error": float(miss["abs_error"]),
                "lead_h": float(miss["lead_h"]),
                "publishTime": miss["publishTime"],
                **d,
            }
        )
    return pd.DataFrame(rows)


def decompose_timing_vs_size(
    joined: pd.DataFrame,
    target: pd.Timestamp,
    shifts_h: tuple[float, ...] = DEFAULT_SHIFTS_H,
    window_h: float = DEFAULT_WINDOW_H,
    timing_threshold: float = TIMING_THRESHOLD,
) -> dict:
    """Would sliding the forecast in time have fixed this miss?

    The forecast curve is shifted by each candidate offset and scored by MAE
    over a local window around ``target``. If the best shift removes at least
    ``timing_threshold`` of the unshifted window MAE, the miss is labelled
    ``"timing"`` -- the forecast had roughly the right shape at roughly the
    wrong time -- otherwise ``"size"``.

    Scoring over a window rather than the single period matters: a shift can
    always make one period look better by pulling in a neighbouring value, so a
    single-period test would call almost everything a timing error.
    """
    df = joined.loc[joined["error"].notna(), ["startTime", "forecast_mw", "actual_mw"]]
    if df.empty:
        return _no_decomposition("no scored rows")

    series = df.set_index("startTime").sort_index()
    lo = target - pd.Timedelta(hours=window_h)
    hi = target + pd.Timedelta(hours=window_h)
    window_actual = series.loc[lo:hi, "actual_mw"]
    if window_actual.empty:
        return _no_decomposition("empty window")

    # Align every candidate shift first, then score them all on the SAME set of
    # periods. Otherwise a shift that drops points off the edge of the window
    # averages over fewer periods than its rivals and can win on sample choice
    # rather than on fit.
    aligned: dict[float, pd.Series] = {}
    for s in shifts_h:
        # Shift the forecast curve forward by s hours: the value that was
        # forecast for (t - s) is compared against the actual at t.
        shifted = series["forecast_mw"].copy()
        shifted.index = shifted.index + pd.Timedelta(hours=s)
        aligned[float(s)] = shifted.reindex(window_actual.index)

    common = window_actual.notna()
    for a in aligned.values():
        common &= a.notna()
    if 0.0 not in aligned or common.sum() < 2:
        return _no_decomposition("insufficient overlap")

    actual_pts = window_actual.loc[common]
    results = {
        s: float((a.loc[common] - actual_pts).abs().mean()) for s, a in aligned.items()
    }

    base = results[0.0]
    # Tie-break towards no shift: a shift has to be strictly better to count,
    # or a flat level error would be blamed on timing by an arbitrary tie.
    best_shift = min(results, key=lambda k: (results[k], abs(k)))
    best = results[best_shift]
    removed = (base - best) / base if base > 0 else 0.0
    is_timing = best_shift != 0.0 and removed >= timing_threshold

    return {
        "window_mae_unshifted_mw": base,
        "best_shift_h": float(best_shift),
        "window_mae_at_best_shift_mw": best,
        "error_removed_by_shift_pct": 100.0 * removed,
        "miss_type": "timing" if is_timing else "size",
        "shift_curve_mw": {float(k): round(v, 1) for k, v in sorted(results.items())},
        "decomposition_note": None,
    }


def _no_decomposition(note: str) -> dict:
    return {
        "window_mae_unshifted_mw": None,
        "best_shift_h": None,
        "window_mae_at_best_shift_mw": None,
        "error_removed_by_shift_pct": None,
        "miss_type": "unknown",
        "shift_curve_mw": {},
        "decomposition_note": note,
    }


def data_quality(
    ingest_report: dict, actuals: pd.DataFrame, forecasts: pd.DataFrame
) -> dict:
    """Coverage, gaps and duplicates: the ingest record plus live re-checks.

    The ingest report is provenance (what the fetch saw); the live checks are
    verification (what the committed snapshot actually contains). Both are
    reported so a discrepancy between them is visible rather than hidden.
    """
    target_from = pd.Timestamp(ingest_report["target_window_utc"][0])
    target_to = pd.Timestamp(ingest_report["target_window_utc"][1])
    expected = pd.date_range(target_from, target_to, freq="30min", inclusive="left")
    present = pd.DatetimeIndex(actuals["startTime"])
    missing = expected.difference(present)

    lead_h = (forecasts["startTime"] - forecasts["publishTime"]).dt.total_seconds() / 3600.0
    per_day = (
        actuals.groupby(actuals["startTime"].dt.strftime("%Y-%m-%d"))["generation"]
        .agg(periods="size", mean_mw="mean", min_mw="min", max_mw="max")
        .reset_index()
        .rename(columns={"startTime": "date"})
    )
    per_day["coverage_pct"] = 100.0 * per_day["periods"] / 48.0

    pub_times = forecasts["publishTime"].drop_duplicates().sort_values()
    pub_clock = pub_times.dt.strftime("%H:%M").value_counts().sort_index()
    pubs_per_day = pub_times.dt.strftime("%Y-%m-%d").value_counts()

    return {
        "ingest_report": ingest_report,
        "live_checks": {
            "actual_rows": int(len(actuals)),
            "actual_periods_expected": int(len(expected)),
            "actual_periods_missing": [t.isoformat() for t in missing],
            "actual_coverage_pct": 100.0 * len(present.unique()) / len(expected),
            "actual_duplicate_start_times": int(actuals["startTime"].duplicated().sum()),
            "forecast_rows": int(len(forecasts)),
            "forecast_duplicate_keys": int(
                forecasts.duplicated(subset=["startTime", "publishTime"]).sum()
            ),
            "forecast_negative_lead_rows": int((lead_h < 0).sum()),
            "forecast_lead_h_min": float(lead_h.min()),
            "forecast_lead_h_max": float(lead_h.max()),
            "distinct_publish_times": int(len(pub_times)),
            "publish_clock_times": pub_clock.to_dict(),
            "days_with_unusual_publish_count": {
                d: int(c)
                for d, c in pubs_per_day.items()
                if c != int(pubs_per_day.median())
            },
            "actual_mw_min": float(actuals["generation"].min()),
            "actual_mw_max": float(actuals["generation"].max()),
            "actual_zero_or_negative_periods": int((actuals["generation"] <= 0).sum()),
        },
        "coverage_per_day": per_day.to_dict(orient="records"),
        "handling": {
            "duplicates": "one row kept per (startTime, publishTime) for forecasts "
                          "and per startTime for actuals, keeping the last after a "
                          "stable sort by publishTime",
            "negative_lead_forecasts": "kept in the snapshot (they are real "
                                       "publications and the historical explorer "
                                       "shows them) but never selected in horizon "
                                       "mode with H >= 0",
            "missing_intervals": "left missing; never interpolated. Metrics report "
                                 "coverage_pct so a gap shrinks the sample visibly "
                                 "instead of being filled with a guess",
            "half_hour_alignment": "hourly WINDFOR held across both half-hours of "
                                   "its hour (config.FORECAST_ALIGNMENT)",
        },
    }
