"""The core rule: which forecast was *live* at a decision cutoff.

For a target (delivery) time T and a cutoff C, the live forecast for T is the
forecast for T with the latest ``publishTime <= C``. A forecast published after
C must never be used for T -- that is lookahead/leakage and it would make every
accuracy number in this app optimistic and useless.

Everything here is a pure function over pandas objects: no FastAPI imports, no
file or network I/O, no reliance on "now". Selection is vectorised through
``pandas.merge_asof`` (backward, by target key), which *is* the core rule:
"last row at or before the key".

Timestamps are timezone-aware UTC throughout. Europe/London is used only to
resolve a day-ahead cutoff clock time, then converted straight back to UTC.
"""

from __future__ import annotations

from datetime import time
from typing import Iterable, Literal

import pandas as pd

from .config import (
    DEFAULT_DAY_AHEAD_CUTOFF_LOCAL,
    FORECAST_ALIGNMENT,
    LONDON_TZ,
)

Mode = Literal["horizon", "day_ahead"]

# Values of the ``reason`` column. REASON_OK means forecast_mw is populated.
REASON_OK = "ok"
REASON_NO_FORECAST_FOR_TARGET = "no_forecast_for_target"
REASON_ALL_FORECASTS_AFTER_CUTOFF = "all_forecasts_after_cutoff"
REASON_OFF_FORECAST_GRID = "target_not_on_forecast_grid"

FORECAST_COLUMNS = ("startTime", "publishTime", "generation")
OUTPUT_COLUMNS = (
    "startTime",
    "cutoff",
    "publishTime",
    "lead_h",
    "forecast_mw",
    "reason",
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _as_utc_index(values: Iterable, label: str) -> pd.DatetimeIndex:
    """Coerce to a tz-aware UTC DatetimeIndex, rejecting naive input."""
    idx = pd.DatetimeIndex(values)
    if idx.tz is None:
        raise ValueError(
            f"{label} must be timezone-aware (UTC); got naive timestamps. "
            "Localise upstream -- naive times are how leakage bugs start."
        )
    return idx.tz_convert("UTC")


def _as_utc_series(s: pd.Series, label: str) -> pd.Series:
    if len(s) == 0:
        # An empty column carries no tz information to check or preserve.
        return pd.Series(pd.DatetimeIndex([], tz="UTC"), index=s.index)
    out = pd.to_datetime(s)
    if out.dt.tz is None:
        raise ValueError(f"{label} must be timezone-aware (UTC); got naive timestamps.")
    return out.dt.tz_convert("UTC")


def align_forecast_grid(targets: pd.DatetimeIndex, alignment: str) -> pd.DatetimeIndex:
    """Map each target time to the forecast ``startTime`` that covers it.

    WINDFOR is hourly; FUELHH actuals are half-hourly. Two defensible choices,
    selected by the single switch ``config.FORECAST_ALIGNMENT``:

    ``"hold"`` (default)
        The hourly forecast is held flat across both half-hours of its hour, so
        target 10:30 is scored against the 10:00 forecast. Keeps every actual
        settlement period in the sample (full coverage of the month, and the
        trading day is settled half-hourly, so this is the grid the desk
        actually lives on). Cost: the two half-hours of an hour share one
        forecast value, so their errors are correlated -- treating them as
        independent samples slightly understates the width of empirical error
        bands, and a genuine within-hour ramp is charged to the forecast as
        error it could not have expressed.

    ``"hourly_points"``
        Only exact hour starts are compared; half-past targets come back with
        ``reason=target_not_on_forecast_grid`` and a null forecast. Cleaner
        statistics (one independent sample per published value) at the cost of
        discarding half the actuals and saying nothing about :30 periods.

    Default is ``"hold"``: this product answers "how much wind can I count on in
    this settlement period", and half of all settlement periods start at :30.
    """
    if alignment == "hold":
        return targets.floor("h")
    if alignment == "hourly_points":
        on_hour = targets == targets.floor("h")
        return pd.DatetimeIndex(targets.where(on_hour))
    raise ValueError(
        f"unknown alignment {alignment!r}; expected 'hold' or 'hourly_points'"
    )


def day_ahead_cutoffs(
    targets: pd.DatetimeIndex, cutoff_local_time: time
) -> pd.DatetimeIndex:
    """Cutoff = ``cutoff_local_time`` on the London day before T's delivery day.

    The delivery day is the London calendar day of T (a 23:30 UTC target in
    summer is already *tomorrow* in London, which is the whole reason this is
    done in local time), so the gap to the cutoff is not always 24h+.
    """
    local = targets.tz_convert(LONDON_TZ)
    prev_day = local.tz_localize(None).normalize() - pd.Timedelta(days=1)
    stamps = prev_day + pd.Timedelta(
        hours=cutoff_local_time.hour,
        minutes=cutoff_local_time.minute,
        seconds=cutoff_local_time.second,
    )
    # ambiguous=True -> the DST (earlier) occurrence; nonexistent -> shift out of
    # the spring-forward gap. Both only bite for cutoff times inside the
    # ~01:00-02:00 London clock-change window; 09:20 is never affected.
    return stamps.tz_localize(
        LONDON_TZ, ambiguous=True, nonexistent="shift_forward"
    ).tz_convert("UTC")


def compute_cutoffs(
    targets: Iterable,
    mode: Mode,
    horizon_h: float | None = None,
    cutoff_local_time: time | None = None,
) -> pd.DatetimeIndex:
    """Decision cutoff C for each target time, in UTC."""
    idx = _as_utc_index(targets, "targets")
    if mode == "horizon":
        if horizon_h is None:
            raise ValueError("horizon mode requires horizon_h")
        if horizon_h < 0:
            raise ValueError(f"horizon_h must be >= 0; got {horizon_h}")
        return idx - pd.Timedelta(hours=float(horizon_h))
    if mode == "day_ahead":
        return day_ahead_cutoffs(
            idx,
            cutoff_local_time
            if cutoff_local_time is not None
            else DEFAULT_DAY_AHEAD_CUTOFF_LOCAL,
        )
    raise ValueError(f"unknown mode {mode!r}; expected 'horizon' or 'day_ahead'")


def normalise_forecasts(forecasts: pd.DataFrame) -> pd.DataFrame:
    """Validate, UTC-normalise and de-duplicate a WINDFOR frame.

    Duplicate ``(startTime, publishTime)`` pairs keep the last row after a
    stable sort. The data-quality panel counts duplicates; selection only has to
    be deterministic about them.
    """
    missing = [c for c in FORECAST_COLUMNS if c not in forecasts.columns]
    if missing:
        raise ValueError(f"forecasts missing columns: {missing}")
    out = forecasts.loc[:, list(FORECAST_COLUMNS)].copy()
    out["startTime"] = _as_utc_series(out["startTime"], "forecasts.startTime")
    out["publishTime"] = _as_utc_series(out["publishTime"], "forecasts.publishTime")
    out["generation"] = pd.to_numeric(out["generation"], errors="coerce")
    out = out.sort_values(["startTime", "publishTime"], kind="mergesort")
    out = out.drop_duplicates(subset=["startTime", "publishTime"], keep="last")
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# the core rule
# --------------------------------------------------------------------------- #
def select_live_forecasts(
    forecasts: pd.DataFrame,
    targets: Iterable,
    mode: Mode,
    horizon_h: float | None = None,
    cutoff_local_time: time | None = None,
    alignment: str | None = None,
) -> pd.DataFrame:
    """One row per target time: the forecast that was live at its cutoff.

    Parameters
    ----------
    forecasts
        WINDFOR rows with tz-aware ``startTime``, ``publishTime``, ``generation``.
    targets
        Target (delivery) times, tz-aware. Input order is preserved.
    mode
        ``"horizon"``   -> cutoff = T - ``horizon_h`` hours.
        ``"day_ahead"`` -> cutoff = ``cutoff_local_time`` (Europe/London) on the
        calendar day before T's London delivery day.
    alignment
        Overrides ``config.FORECAST_ALIGNMENT``; see :func:`align_forecast_grid`.

    Returns
    -------
    DataFrame with columns ``startTime, cutoff, publishTime, lead_h,
    forecast_mw, reason``. Targets with no eligible forecast are **kept** with
    nulls and a ``reason``, never dropped: missing coverage is a finding to
    report, not something to hide by shrinking the sample.
    """
    alignment = FORECAST_ALIGNMENT if alignment is None else alignment
    target_idx = _as_utc_index(targets, "targets")
    cutoffs = compute_cutoffs(target_idx, mode, horizon_h, cutoff_local_time)

    left = pd.DataFrame(
        {
            "startTime": target_idx,
            "cutoff": cutoffs,
            "fc_key": align_forecast_grid(target_idx, alignment),
            "_order": range(len(target_idx)),
        }
    )

    fc = normalise_forecasts(forecasts).rename(columns={"startTime": "fc_key"})
    on_grid = left.loc[left["fc_key"].notna()]

    if len(fc) and len(on_grid):
        asof = pd.merge_asof(
            on_grid.sort_values("cutoff", kind="mergesort"),
            fc.sort_values("publishTime", kind="mergesort"),
            left_on="cutoff",
            right_on="publishTime",
            by="fc_key",
            direction="backward",
            allow_exact_matches=True,  # publishTime == cutoff is eligible
        )
        # Earliest publication per target key, to tell "nothing published yet at
        # this cutoff" apart from "no forecast for this target at all".
        first_pub = fc.groupby("fc_key")["publishTime"].min().rename("_first_pub")
        asof = asof.join(first_pub, on="fc_key")
        out = left.merge(
            asof[["_order", "publishTime", "generation", "_first_pub"]],
            on="_order",
            how="left",
        )
    else:
        out = left.assign(publishTime=pd.NaT, generation=float("nan"), _first_pub=pd.NaT)

    out = out.sort_values("_order", kind="mergesort").reset_index(drop=True)
    out["publishTime"] = pd.to_datetime(out["publishTime"], utc=True)
    out["_first_pub"] = pd.to_datetime(out["_first_pub"], utc=True)
    out["forecast_mw"] = pd.to_numeric(out["generation"], errors="coerce")
    out["lead_h"] = (out["startTime"] - out["publishTime"]).dt.total_seconds() / 3600.0

    off_grid = out["fc_key"].isna()
    have = out["publishTime"].notna()
    nothing_yet = ~have & out["_first_pub"].notna()
    out["reason"] = REASON_NO_FORECAST_FOR_TARGET
    out.loc[have, "reason"] = REASON_OK
    out.loc[nothing_yet, "reason"] = REASON_ALL_FORECASTS_AFTER_CUTOFF
    out.loc[off_grid, "reason"] = REASON_OFF_FORECAST_GRID

    return out.loc[:, list(OUTPUT_COLUMNS)]


def forecast_vintages(
    forecasts: pd.DataFrame,
    target: pd.Timestamp,
    cutoff: pd.Timestamp | None = None,
    alignment: str | None = None,
) -> pd.DataFrame:
    """Every forecast ever published for one target time (historical explorer).

    Columns: ``publishTime, forecast_mw, lead_h, eligible, is_live``.
    ``is_live`` marks the one row the core rule picks at ``cutoff``.
    """
    alignment = FORECAST_ALIGNMENT if alignment is None else alignment
    t = _as_utc_index([target], "target")[0]
    key = align_forecast_grid(pd.DatetimeIndex([t]), alignment)[0]
    fc = normalise_forecasts(forecasts)
    rows = fc.loc[fc["startTime"] == key] if pd.notna(key) else fc.iloc[0:0]

    out = pd.DataFrame(
        {
            "publishTime": pd.to_datetime(rows["publishTime"].to_numpy(), utc=True),
            "forecast_mw": rows["generation"].to_numpy(),
        }
    )
    out["lead_h"] = (t - out["publishTime"]).dt.total_seconds() / 3600.0
    if cutoff is None:
        out["eligible"] = pd.NA
        out["is_live"] = False
    else:
        c = _as_utc_index([cutoff], "cutoff")[0]
        out["eligible"] = out["publishTime"] <= c
        live = (
            out.loc[out["eligible"], "publishTime"].max()
            if bool(out["eligible"].any())
            else pd.NaT
        )
        out["is_live"] = out["eligible"] & (out["publishTime"] == live)
    return out.sort_values("publishTime", kind="mergesort").reset_index(drop=True)
