"""Empirical uncertainty bands, calibrated walk-forward, and the buying plan.

Bands come from the forecast's own track record, not from a distributional
assumption: for a target in week k we take the empirical quantiles of the
errors observed in weeks strictly before k, within the same horizon bucket, and
subtract them from the forecast.

Direction matters and is easy to get backwards. With ``error = forecast -
actual``, we have ``actual = forecast - error``, so the LOW quantile of the
predicted actual comes from the HIGH quantile of the error:

    P10(actual) = forecast - Q90(error)

The desk cares about the low end -- that is the wind you can count on.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

# Horizon buckets for the error distribution. Wide enough to hold a decent
# sample in a one-month snapshot, narrow enough that a 2h-ahead forecast is not
# pooled with a 40h-ahead one.
DEFAULT_HORIZON_BUCKETS: tuple[float, ...] = (0, 6, 12, 24, 36, 48, np.inf)
WEEK = pd.Timedelta(days=7)

BAND_QUANTILES: tuple[float, ...] = (0.10, 0.25, 0.50, 0.75, 0.90)

#: Nominal central intervals we check calibration against.
NOMINAL_INTERVALS: tuple[tuple[str, str, float], ...] = (
    ("p10", "p90", 0.80),
    ("p25", "p75", 0.50),
)


def assign_week(targets: pd.Series, origin: pd.Timestamp | None = None) -> pd.Series:
    """Zero-based week index in fixed 7-day blocks from the first target.

    Fixed blocks from the data's own start, not ISO weeks: it keeps the
    warm-up period to exactly one block and makes "weeks < k" unambiguous at
    the month boundary.
    """
    origin = pd.Timestamp(targets.min()) if origin is None else origin
    return ((targets - origin) // WEEK).astype("int64")


def assign_horizon_bucket(
    lead_h: pd.Series, buckets: Sequence[float] = DEFAULT_HORIZON_BUCKETS
) -> pd.Series:
    return pd.cut(lead_h, bins=list(buckets), right=False)


def walk_forward_bands(
    joined: pd.DataFrame,
    buckets: Sequence[float] = DEFAULT_HORIZON_BUCKETS,
    quantiles: Sequence[float] = BAND_QUANTILES,
    min_samples: int = 20,
) -> pd.DataFrame:
    """Add predicted-actual band columns to a joined frame, walk-forward.

    For each (week k, horizon bucket) the error quantiles are estimated from
    rows in weeks < k only. Week 0 has no history, so it falls back to a
    distribution pooled over the whole sample and is flagged
    ``band_basis == "warm-up"``.

    **The warm-up fallback does use data from its own and later weeks.** There
    is no honest alternative inside a one-month snapshot -- week 0 has nothing
    earlier to learn from -- so rather than pretend, those rows are flagged and
    :func:`calibration` excludes them by default. Any accuracy claim made on
    warm-up rows is optimistic and must say so.

    A (week, bucket) cell with fewer than ``min_samples`` prior errors falls
    back to all prior weeks pooled across buckets (still strictly earlier, so
    still leakage-free) and is flagged ``"pooled-prior"``.

    Returns the input frame plus: ``week``, ``horizon_bucket``, ``p10``...``p90``
    (MW of predicted actual), ``band_basis``, ``band_n`` (sample size behind
    the band) and ``band_source_max_target`` -- the latest target time whose
    error fed the band, which is what the no-lookahead test asserts on.
    """
    df = joined.copy()
    df["week"] = assign_week(df["startTime"])
    df["horizon_bucket"] = assign_horizon_bucket(df["lead_h"], buckets)

    scored = df.loc[df["error"].notna()]
    # dict, so a caller asking for the same quantile twice gets one column
    qmap = {f"p{int(round(q * 100))}": float(q) for q in quantiles}
    qcols = list(qmap)
    for c in qcols + ["band_n", "band_source_max_target", "band_basis"]:
        df[c] = np.nan if c not in ("band_basis", "band_source_max_target") else pd.NA

    for (week, bucket), idx in df.groupby(
        ["week", "horizon_bucket"], observed=True, sort=True
    ).groups.items():
        prior = scored.loc[scored["week"] < week]
        in_bucket = prior.loc[prior["horizon_bucket"] == bucket]

        if len(in_bucket) >= min_samples:
            source, basis = in_bucket, "walk-forward"
        elif len(prior) >= min_samples:
            source, basis = prior, "pooled-prior"
        else:
            # Week 0 (or a bucket with almost no history): no earlier data.
            source, basis = scored.loc[scored["horizon_bucket"] == bucket], "warm-up"
            if len(source) < min_samples:
                source = scored

        if source.empty:
            continue

        errs = source["error"].to_numpy(dtype=float)
        # actual = forecast - error, so the q-quantile of the predicted actual
        # comes from the (1 - q)-quantile of the error. Done per column rather
        # than by reversing the array: reversal only happens to be right for a
        # symmetric quantile set, and silently inverts a single-quantile call.
        for col, q in qmap.items():
            df.loc[idx, col] = df.loc[idx, "forecast_mw"] - np.quantile(errs, 1.0 - q)
        df.loc[idx, "band_n"] = len(source)
        df.loc[idx, "band_basis"] = basis
        df.loc[idx, "band_source_max_target"] = source["startTime"].max()

    df["band_source_max_target"] = pd.to_datetime(
        df["band_source_max_target"], utc=True
    )
    return df


def calibration(
    banded: pd.DataFrame,
    intervals: Sequence[tuple[str, str, float]] = NOMINAL_INTERVALS,
    exclude_warmup: bool = True,
) -> pd.DataFrame:
    """Did the bands do what they promised?

    Reported as-is. An 80% band that contains 74% of outcomes is a finding to
    put in front of the desk, not a number to tune until it looks right.
    """
    df = banded.loc[banded["error"].notna()]
    if exclude_warmup:
        df = df.loc[df["band_basis"] != "warm-up"]
    rows = []
    for lo, hi, nominal in intervals:
        usable = df.loc[df[lo].notna() & df[hi].notna()]
        inside = (usable["actual_mw"] >= usable[lo]) & (usable["actual_mw"] <= usable[hi])
        n = len(usable)
        rows.append(
            {
                "interval": f"{lo.upper()}-{hi.upper()}",
                "nominal_pct": 100.0 * nominal,
                "empirical_pct": 100.0 * float(inside.mean()) if n else None,
                "n": n,
                "miss_low_pct": 100.0 * float((usable["actual_mw"] < usable[lo]).mean()) if n else None,
                "miss_high_pct": 100.0 * float((usable["actual_mw"] > usable[hi]).mean()) if n else None,
            }
        )
    return pd.DataFrame(rows)


def plan_on(
    banded: pd.DataFrame,
    confidence: float,
    buckets: Sequence[float] = DEFAULT_HORIZON_BUCKETS,
    min_samples: int = 20,
) -> pd.DataFrame:
    """The MW of wind you can count on, per period, at a given confidence.

    ``confidence=0.90`` means "wind should be at least this, 90% of the time",
    i.e. the 10th percentile of the predicted actual: ``forecast - Q90(error)``.
    Quantiles are re-derived walk-forward at the exact level asked for rather
    than interpolated between stored bands.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1); got {confidence}")
    out = walk_forward_bands(
        banded, buckets=buckets, quantiles=(1.0 - confidence,), min_samples=min_samples
    )
    col = f"p{int(round((1.0 - confidence) * 100))}"
    out = out.rename(columns={col: "plan_mw"})
    out["confidence"] = confidence
    return out.loc[
        :,
        ["startTime", "cutoff", "lead_h", "forecast_mw", "actual_mw", "plan_mw",
         "confidence", "band_basis", "band_n"],
    ]


def newsvendor_quantile(shortfall_to_surplus_cost_ratio: float) -> float:
    """Critical fractile ``q = r / (1 + r)`` for the quantity to buy.

    ``r`` is how much worse being short is than being long, per MW. r=1 gives
    0.5 (the median -- symmetric costs), r=3 gives 0.75.

    Note the frame: ``q`` is the quantile of **residual demand to cover**. Wind
    is the thing being subtracted, so the matching wind quantile is ``1 - q``:
    the more you fear a shortfall, the LOWER the wind figure you plan on. The
    mapping is applied in :func:`plan_at_cost_ratio`.
    """
    r = float(shortfall_to_surplus_cost_ratio)
    if r <= 0:
        raise ValueError(f"cost ratio must be > 0; got {r}")
    return r / (1.0 + r)


def plan_at_cost_ratio(
    banded: pd.DataFrame,
    shortfall_to_surplus_cost_ratio: float,
    buckets: Sequence[float] = DEFAULT_HORIZON_BUCKETS,
    min_samples: int = 20,
) -> pd.DataFrame:
    """Cost-aware plan: the newsvendor quantile instead of the median.

    Adds ``plan_mw`` at the cost-implied quantile and ``median_plan_mw`` (r=1)
    alongside, plus ``shift_vs_median_mw``, so the UI can show how much the plan
    moves once shortfall is priced as worse than surplus.
    """
    q = newsvendor_quantile(shortfall_to_surplus_cost_ratio)
    wind_q = 1.0 - q  # see newsvendor_quantile docstring
    plan = walk_forward_bands(
        banded, buckets=buckets, quantiles=(wind_q, 0.5), min_samples=min_samples
    )
    qcol = f"p{int(round(wind_q * 100))}"
    if qcol == "p50":  # r == 1: the cost-aware plan *is* the median
        out = plan.rename(columns={"p50": "plan_mw"})
        out["median_plan_mw"] = out["plan_mw"]
    else:
        out = plan.rename(columns={qcol: "plan_mw", "p50": "median_plan_mw"})
    out["newsvendor_q"] = q
    out["wind_quantile"] = wind_q
    out["cost_ratio"] = float(shortfall_to_surplus_cost_ratio)
    out["shift_vs_median_mw"] = out["plan_mw"] - out["median_plan_mw"]
    return out.loc[
        :,
        ["startTime", "cutoff", "lead_h", "forecast_mw", "actual_mw", "plan_mw",
         "median_plan_mw", "shift_vs_median_mw", "cost_ratio", "newsvendor_q",
         "wind_quantile", "band_basis", "band_n"],
    ]


def shortfall_summary(plan: pd.DataFrame) -> dict:
    """How the plan would have fared: shortfall frequency and size.

    A shortfall is ``actual < plan`` -- the desk counted on wind that did not
    arrive and has to cover it at the expensive end.
    """
    df = plan.loc[plan["plan_mw"].notna() & plan["actual_mw"].notna()]
    if df.empty:
        return {"n": 0}
    gap = df["actual_mw"] - df["plan_mw"]
    short = gap < 0
    return {
        "n": int(len(df)),
        "shortfall_rate_pct": 100.0 * float(short.mean()),
        "mean_shortfall_mw": float(-gap[short].mean()) if short.any() else 0.0,
        "worst_shortfall_mw": float(-gap.min()) if short.any() else 0.0,
        "mean_surplus_mw": float(gap[~short].mean()) if (~short).any() else 0.0,
        "mean_headroom_left_on_table_mw": float(gap.mean()),
    }
