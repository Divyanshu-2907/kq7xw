#!/usr/bin/env python
"""Run the whole analysis engine over the committed snapshot and print findings.

Reporting tool, not part of the API. Numbers are printed at the precision they
come out at; nothing is rounded to look tidier than it is.
"""

from __future__ import annotations

import sys
from datetime import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis import biggest_misses, data_quality  # noqa: E402
from app.bands import (  # noqa: E402
    calibration,
    plan_at_cost_ratio,
    plan_on,
    shortfall_summary,
    walk_forward_bands,
)
from app.data import load_actuals, load_forecasts, load_ingest_report  # noqa: E402
from app.metrics import (  # noqa: E402
    compute_metrics,
    error_by_horizon,
    error_by_hour_of_day,
    error_by_wind_level,
    join_actuals,
)
from app.selection import select_live_forecasts  # noqa: E402

HORIZONS = [0, 1, 2, 3, 4, 6, 9, 12, 18, 24, 30, 36, 42, 48]
pd.set_option("display.width", 200, "display.max_columns", 50)


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def main() -> int:
    actuals, forecasts = load_actuals(), load_forecasts()
    report = load_ingest_report()

    rule("1. ERROR vs HORIZON  (no-lookahead selection re-run independently per H)")
    by_h = error_by_horizon(forecasts, actuals, HORIZONS)
    print(
        by_h.to_string(
            index=False,
            formatters={
                "horizon_h": "{:.0f}".format,
                "coverage_pct": "{:.1f}".format,
                "mae_mw": "{:.1f}".format,
                "rmse_mw": "{:.1f}".format,
                "bias_mw": "{:+.1f}".format,
                "nmae_pct": "{:.2f}".format,
                "p50_abs_error_mw": "{:.1f}".format,
                "p90_abs_error_mw": "{:.1f}".format,
                "mean_actual_mw": "{:.0f}".format,
                "mean_lead_h": "{:.1f}".format,
            },
        )
    )
    full = by_h.loc[by_h["coverage_pct"] > 99]
    if len(full) > 1:
        lo, hi = full.iloc[0], full.iloc[-1]
        span = hi["horizon_h"] - lo["horizon_h"]
        print(
            f"\n  value of waiting: MAE {lo['mae_mw']:.1f} MW at H={lo['horizon_h']:.0f}h "
            f"-> {hi['mae_mw']:.1f} MW at H={hi['horizon_h']:.0f}h "
            f"= {(hi['mae_mw'] - lo['mae_mw']) / span:+.1f} MW per hour of waiting "
            f"({(hi['mae_mw'] - lo['mae_mw']) / lo['mae_mw'] * 100:+.1f}% over {span:.0f}h)"
        )

    rule("2. DAY-AHEAD MODE: the ten minutes between the two GB gate closures")
    for label, t in (("EPEX 09:20", time(9, 20)), ("N2EX 09:50", time(9, 50))):
        sel = select_live_forecasts(
            forecasts, actuals["startTime"], "day_ahead", cutoff_local_time=t
        )
        j = join_actuals(sel, actuals)
        m = compute_metrics(j)
        live_clock = (
            j.loc[j["error"].notna(), "publishTime"].dt.strftime("%H:%M").value_counts()
        )
        print(
            f"  {label}: MAE {m['mae_mw']:.1f} MW | RMSE {m['rmse_mw']:.1f} | "
            f"bias {m['bias_mw']:+.1f} | nMAE {m['nmae_pct']:.2f}% | "
            f"mean lead {j.loc[j['error'].notna(), 'lead_h'].mean():.1f}h | "
            f"n={m['count']} cov={m['coverage_pct']:.1f}%"
        )
        print(f"      vintages actually used: {live_clock.to_dict()}")

    rule("3. ERROR BY HOUR OF DAY (London) and BY FORECAST WIND LEVEL, at H=24h")
    sel24 = select_live_forecasts(forecasts, actuals["startTime"], "horizon", horizon_h=24)
    j24 = join_actuals(sel24, actuals)
    hod = error_by_hour_of_day(j24)
    print(hod.loc[:, ["hour", "count", "mae_mw", "bias_mw", "mean_actual_mw"]].to_string(
        index=False, formatters={"mae_mw": "{:.1f}".format, "bias_mw": "{:+.1f}".format,
                                 "mean_actual_mw": "{:.0f}".format}))
    print()
    wl = error_by_wind_level(j24)
    print(wl.loc[:, ["wind_level", "count", "mae_mw", "bias_mw", "nmae_pct", "mean_actual_mw"]].to_string(
        index=False, formatters={"mae_mw": "{:.1f}".format, "bias_mw": "{:+.1f}".format,
                                 "nmae_pct": "{:.2f}".format, "mean_actual_mw": "{:.0f}".format}))

    rule("4. WALK-FORWARD BAND CALIBRATION (H=24h, week 0 excluded as warm-up)")
    banded = walk_forward_bands(j24)
    print("  band basis counts:", banded["band_basis"].value_counts(dropna=False).to_dict())
    cal = calibration(banded)
    for _, r in cal.iterrows():
        print(
            f"  {r['interval']} should contain {r['nominal_pct']:.0f}% -- it contains "
            f"{r['empirical_pct']:.1f}%  (n={r['n']}, "
            f"{r['miss_low_pct']:.1f}% below, {r['miss_high_pct']:.1f}% above)"
        )

    rule("5. PLAN ON X MW, and the cost-aware shift")
    for conf in (0.5, 0.8, 0.9, 0.95):
        p = plan_on(j24, conf)
        usable = p.loc[p["band_basis"] != "warm-up"]
        s = shortfall_summary(usable)
        print(
            f"  confidence {conf:.0%}: mean plan {usable['plan_mw'].mean():.1f} MW "
            f"(mean forecast {usable['forecast_mw'].mean():.1f}) | "
            f"actual fell short {s['shortfall_rate_pct']:.1f}% of periods"
        )
    print()
    for r_ratio in (1.0, 2.0, 3.0, 5.0):
        p = plan_at_cost_ratio(j24, r_ratio)
        usable = p.loc[p["band_basis"] != "warm-up"]
        s = shortfall_summary(usable)
        print(
            f"  r={r_ratio:.0f} (q={p['newsvendor_q'].iloc[0]:.3f}, wind quantile "
            f"{p['wind_quantile'].iloc[0]:.3f}): plan {usable['plan_mw'].mean():.1f} MW, "
            f"{usable['shift_vs_median_mw'].mean():+.1f} MW vs median, "
            f"shortfall {s['shortfall_rate_pct']:.1f}% of periods"
        )

    rule("6. BIGGEST MISSES at the 09:20 day-ahead gate (what the desk actually faced)")
    sel_da = select_live_forecasts(
        forecasts, actuals["startTime"], "day_ahead", cutoff_local_time=time(9, 20)
    )
    j_da = join_actuals(sel_da, actuals)
    misses = biggest_misses(j_da, n=10)
    for i, m in misses.iterrows():
        print(
            f"  {i + 1:2d}. {m['startTime']:%Y-%m-%d %H:%M} UTC  "
            f"forecast {m['forecast_mw']:7.0f}  actual {m['actual_mw']:7.0f}  "
            f"error {m['error']:+8.0f} MW  lead {m['lead_h']:5.1f}h  "
            f"{m['miss_type']:7s} best_shift {m['best_shift_h']:+.0f}h "
            f"removes {m['error_removed_by_shift_pct']:5.1f}%"
        )
    print("\n  miss types:", misses["miss_type"].value_counts().to_dict())
    print("  worst three, shift curves (window MAE in MW by shift in h):")
    for _, m in misses.head(3).iterrows():
        print(f"    {m['startTime']:%Y-%m-%d %H:%M}: {m['shift_curve_mw']}")

    rule("7. DATA QUALITY")
    dq = data_quality(report, actuals, forecasts)
    live = dq["live_checks"]
    for k in (
        "actual_rows", "actual_periods_expected", "actual_coverage_pct",
        "actual_duplicate_start_times", "forecast_rows", "forecast_duplicate_keys",
        "forecast_negative_lead_rows", "forecast_lead_h_min", "forecast_lead_h_max",
        "distinct_publish_times", "actual_mw_min", "actual_mw_max",
        "actual_zero_or_negative_periods", "days_with_unusual_publish_count",
    ):
        print(f"  {k}: {live[k]}")
    print(f"  missing intervals: {len(live['actual_periods_missing'])}")
    print(f"  publish clock times: {live['publish_clock_times']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
