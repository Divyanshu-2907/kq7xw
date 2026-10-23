"""Accuracy metrics. Pure functions over pandas frames, no FastAPI, no I/O.

Error convention throughout the codebase: ``error = forecast - actual``, so a
**positive error means the forecast was too high** (over-forecast), which on a
trading desk is the direction that leaves you short.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .config import LONDON_TZ
from .selection import REASON_OK, select_live_forecasts

# MAPE is deliberately absent. Wind output goes near zero often enough that
# dividing by the actual explodes: a 200 MW miss on a 50 MW hour is 400% and
# would dominate any average. We normalise by the MEAN actual of the sample
# instead (nMAE), which is stable and still answers "how big is the error
# relative to the wind we typically get".
DEFAULT_WIND_LEVEL_EDGES: tuple[float, ...] = (0, 2000, 5000, 8000, 11000, 14000, np.inf)


def join_actuals(selected: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Attach actual MW and signed error to the output of ``select_live_forecasts``.

    Rows with no eligible forecast are kept (their ``error`` is NaN); dropping
    them would quietly flatter every metric computed downstream.
    """
    act = actuals.loc[:, ["startTime", "generation"]].rename(
        columns={"generation": "actual_mw"}
    )
    out = selected.merge(act, on="startTime", how="left")
    out["error"] = out["forecast_mw"] - out["actual_mw"]
    out["abs_error"] = out["error"].abs()
    return out


def compute_metrics(joined: pd.DataFrame) -> dict:
    """Headline accuracy for a joined frame.

    ``coverage_pct`` is the share of requested target periods that actually got
    both a live forecast and an actual -- the denominator every other number
    here is conditioned on.
    """
    total = len(joined)
    scored = joined.loc[joined["error"].notna()]
    n = len(scored)
    if n == 0:
        return {
            "count": 0,
            "coverage_pct": 0.0,
            "mae_mw": None,
            "rmse_mw": None,
            "bias_mw": None,
            "nmae_pct": None,
            "p50_abs_error_mw": None,
            "p90_abs_error_mw": None,
            "mean_actual_mw": None,
        }
    err = scored["error"].to_numpy(dtype=float)
    abs_err = np.abs(err)
    mean_actual = float(scored["actual_mw"].mean())
    return {
        "count": n,
        "coverage_pct": 100.0 * n / total if total else 0.0,
        "mae_mw": float(abs_err.mean()),
        "rmse_mw": float(np.sqrt(np.mean(err**2))),
        "bias_mw": float(err.mean()),
        "nmae_pct": 100.0 * float(abs_err.mean()) / mean_actual if mean_actual else None,
        "p50_abs_error_mw": float(np.quantile(abs_err, 0.50)),
        "p90_abs_error_mw": float(np.quantile(abs_err, 0.90)),
        "mean_actual_mw": mean_actual,
    }


def max_supported_horizon(forecasts: pd.DataFrame, actuals: pd.DataFrame) -> float:
    """Largest lead time, in hours, that any forecast in the snapshot offers."""
    lead = (forecasts["startTime"] - forecasts["publishTime"]).dt.total_seconds() / 3600.0
    return float(lead.max())


def error_by_horizon(
    forecasts: pd.DataFrame,
    actuals: pd.DataFrame,
    horizons: Iterable[float],
    alignment: str | None = None,
) -> pd.DataFrame:
    """Metrics per horizon H, each from an independent no-lookahead selection.

    ``coverage_pct`` is reported per horizon rather than filtered away: at long
    horizons fewer targets have any eligible forecast, and that thinning is
    itself a finding ("the value of waiting" is partly a coverage story).
    """
    targets = actuals["startTime"]
    rows = []
    for h in horizons:
        selected = select_live_forecasts(
            forecasts, targets, "horizon", horizon_h=h, alignment=alignment
        )
        joined = join_actuals(selected, actuals)
        m = compute_metrics(joined)
        m["horizon_h"] = float(h)
        m["mean_lead_h"] = float(joined.loc[joined["error"].notna(), "lead_h"].mean())
        rows.append(m)
    cols = ["horizon_h", "count", "coverage_pct", "mae_mw", "rmse_mw", "bias_mw",
            "nmae_pct", "p50_abs_error_mw", "p90_abs_error_mw", "mean_actual_mw",
            "mean_lead_h"]
    return pd.DataFrame(rows).loc[:, cols]


def error_by_hour_of_day(joined: pd.DataFrame, tz: str = LONDON_TZ) -> pd.DataFrame:
    """Metrics grouped by local hour of the delivery period.

    Local, not UTC: a diurnal pattern is a story about the day the desk works
    in. (In January the two coincide; the distinction matters off-scope.)
    """
    df = joined.copy()
    df["hour"] = df["startTime"].dt.tz_convert(tz).dt.hour
    return _grouped_metrics(df, "hour").sort_values("hour").reset_index(drop=True)


def error_by_wind_level(
    joined: pd.DataFrame, edges: Sequence[float] = DEFAULT_WIND_LEVEL_EDGES
) -> pd.DataFrame:
    """Metrics bucketed by FORECAST MW.

    Bucketing by forecast, not actual, is the point: at decision time the
    forecast is all the desk has, so "how wrong is the forecast when it
    promises 12 GW" is an answerable question and "...when the actual turns out
    to be 12 GW" is not.
    """
    df = joined.copy()
    df["wind_level"] = pd.cut(df["forecast_mw"], bins=list(edges), right=False)
    out = _grouped_metrics(df, "wind_level", observed=False)
    out["wind_level"] = out["wind_level"].astype(str)
    return out.reset_index(drop=True)


def _grouped_metrics(df: pd.DataFrame, key: str, observed: bool = True) -> pd.DataFrame:
    rows = []
    for value, grp in df.groupby(key, observed=observed, sort=True):
        m = compute_metrics(grp)
        m[key] = value
        rows.append(m)
    cols = [key, "count", "coverage_pct", "mae_mw", "rmse_mw", "bias_mw", "nmae_pct",
            "p50_abs_error_mw", "p90_abs_error_mw", "mean_actual_mw"]
    return pd.DataFrame(rows).loc[:, cols]
