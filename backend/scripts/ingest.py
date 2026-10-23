#!/usr/bin/env python
"""Fetch the Elexon BMRS wind snapshot once, commit it, never call Elexon again.

Probed against the live API on 2026-10-23 (see docstrings below and the
parameter names in Elexon's own schema at
https://data.elexon.co.uk/swagger/v1/swagger.json):

FUELHH  /datasets/FUELHH?settlementDateFrom=&settlementDateTo=&fuelType=WIND
    Half-hourly. One row per settlement period, 48 per day, published 30
    minutes after the period starts. Fields: dataset, publishTime, startTime,
    settlementDate, settlementPeriod, fuelType, generation (MW).

WINDFOR /datasets/WINDFOR?publishDateTimeFrom=&publishDateTimeTo=
    Hourly. Filterable ONLY by publish time -- there is no startTime filter --
    so we fetch by publish window and filter target times client-side.
    Each publication carries 73 hourly rows spanning a fixed absolute window
    from 21:00 on D-1 to 21:00 on D+2 (so later publications on a day have
    shorter maximum lead, and early rows have NEGATIVE lead: they describe
    hours that have already happened). Fields: dataset, publishTime,
    startTime, generation (MW).

Usage:
    python backend/scripts/ingest.py             # skip if snapshot exists
    python backend/scripts/ingest.py --force     # refetch
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ACTUALS_PATH = DATA_DIR / "actuals.csv.gz"
FORECASTS_PATH = DATA_DIR / "forecasts.csv.gz"
REPORT_PATH = DATA_DIR / "ingest_report.json"

# Target (delivery) window: January 2026. London == UTC throughout January,
# so the UTC half-open interval is also the London calendar month.
TARGET_FROM = pd.Timestamp("2026-01-01T00:00Z")
TARGET_TO = pd.Timestamp("2026-02-01T00:00Z")  # exclusive

# A WINDFOR publication reaches out to 21:00 on D+2, i.e. up to ~66.5h of lead,
# so publications from 30 Dec 2025 are the earliest that can mention 1 Jan.
# Start a couple of days earlier than strictly needed and filter by startTime.
PUBLISH_FROM = pd.Timestamp("2025-12-28T00:00Z")
PUBLISH_TO = pd.Timestamp("2026-02-01T00:00Z")

CHUNK = pd.Timedelta(days=7)
POLITE_DELAY_S = 1.0
RETRIES = 4


def _get(path: str, params: dict[str, str]) -> list[dict]:
    """GET with retries and exponential backoff. Returns the `data` list."""
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(params, doseq=True)
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.load(resp)
            return payload.get("data", [])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last = exc
            wait = 2.0 * (attempt + 1)
            print(f"  retry {attempt + 1}/{RETRIES} after {exc} (sleep {wait}s)")
            time.sleep(wait)
    raise RuntimeError(f"giving up on {url}: {last}")


def _chunks(start: pd.Timestamp, end: pd.Timestamp):
    cur = start
    while cur < end:
        nxt = min(cur + CHUNK, end)
        yield cur, nxt
        cur = nxt


def fetch_actuals() -> pd.DataFrame:
    """FUELHH WIND for every settlement period in the target month."""
    rows: list[dict] = []
    for lo, hi in _chunks(TARGET_FROM, TARGET_TO):
        # settlementDateTo is inclusive; step back a day so chunks do not overlap
        params = {
            "settlementDateFrom": lo.strftime("%Y-%m-%d"),
            "settlementDateTo": (hi - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            "fuelType": "WIND",
            "format": "json",
        }
        got = _get("FUELHH", params)
        print(f"  FUELHH {params['settlementDateFrom']}..{params['settlementDateTo']}: {len(got)} rows")
        rows.extend(got)
        time.sleep(POLITE_DELAY_S)
    return pd.DataFrame(rows)


def fetch_forecasts() -> pd.DataFrame:
    """WINDFOR across the publish window needed to cover the target month."""
    rows: list[dict] = []
    for lo, hi in _chunks(PUBLISH_FROM, PUBLISH_TO):
        params = {
            "publishDateTimeFrom": lo.strftime("%Y-%m-%dT%H:%MZ"),
            "publishDateTimeTo": hi.strftime("%Y-%m-%dT%H:%MZ"),
            "format": "json",
        }
        got = _get("WINDFOR", params)
        print(f"  WINDFOR publish {params['publishDateTimeFrom']}..{params['publishDateTimeTo']}: {len(got)} rows")
        rows.extend(got)
        time.sleep(POLITE_DELAY_S)
    return pd.DataFrame(rows)


def _utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True)


def normalise(
    actuals_raw: pd.DataFrame, forecasts_raw: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """UTC-normalise, restrict to the target month, dedupe, sort, and report."""
    report: dict = {}

    # --- actuals ---
    a = actuals_raw.copy()
    a["startTime"] = _utc(a["startTime"])
    a["publishTime"] = _utc(a["publishTime"])
    a["generation"] = pd.to_numeric(a["generation"], errors="coerce")
    a = a.loc[(a["startTime"] >= TARGET_FROM) & (a["startTime"] < TARGET_TO)]
    a = a.loc[a["fuelType"] == "WIND"]
    a_rows_before = len(a)
    a = a.sort_values(["startTime", "publishTime"], kind="mergesort")
    a = a.drop_duplicates(subset=["startTime"], keep="last")
    report["actuals_duplicates_dropped"] = a_rows_before - len(a)
    a = a.loc[:, ["startTime", "settlementDate", "settlementPeriod", "generation"]]
    a = a.reset_index(drop=True)

    # --- forecasts ---
    f = forecasts_raw.copy()
    f["startTime"] = _utc(f["startTime"])
    f["publishTime"] = _utc(f["publishTime"])
    f["generation"] = pd.to_numeric(f["generation"], errors="coerce")
    report["forecast_rows_fetched"] = len(f)
    f = f.loc[(f["startTime"] >= TARGET_FROM) & (f["startTime"] < TARGET_TO)]
    report["forecast_rows_in_target_month"] = len(f)
    f_rows_before = len(f)
    f = f.sort_values(["startTime", "publishTime"], kind="mergesort")
    f = f.drop_duplicates(subset=["startTime", "publishTime"], keep="last")
    report["forecast_duplicates_dropped"] = f_rows_before - len(f)
    f = f.loc[:, ["startTime", "publishTime", "generation"]].reset_index(drop=True)

    # --- coverage / resolution / leads ---
    expected = pd.date_range(TARGET_FROM, TARGET_TO, freq="30min", inclusive="left")
    missing = expected.difference(pd.DatetimeIndex(a["startTime"]))
    a_steps = pd.Series(a["startTime"].diff().dropna().unique())
    f_steps = (
        f.sort_values(["publishTime", "startTime"])
        .groupby("publishTime")["startTime"]
        .apply(lambda s: s.diff().dropna().unique())
    )
    f_step_set = sorted({str(x) for arr in f_steps for x in arr})

    lead_h = (f["startTime"] - f["publishTime"]).dt.total_seconds() / 3600.0
    pubs_per_day = (
        f.groupby(f["publishTime"].dt.strftime("%Y-%m-%d"))["publishTime"]
        .nunique()
        .to_dict()
    )
    coverage_per_day = (
        a.groupby(a["startTime"].dt.strftime("%Y-%m-%d"))["generation"].size().to_dict()
    )

    report.update(
        {
            "generated_at_utc": pd.Timestamp.utcnow().isoformat(),
            "source": {
                "base_url": BASE,
                "actuals": "FUELHH?settlementDateFrom=&settlementDateTo=&fuelType=WIND",
                "forecasts": "WINDFOR?publishDateTimeFrom=&publishDateTimeTo=",
            },
            "target_window_utc": [TARGET_FROM.isoformat(), TARGET_TO.isoformat()],
            "publish_window_utc": [PUBLISH_FROM.isoformat(), PUBLISH_TO.isoformat()],
            "actual_rows": len(a),
            "forecast_rows": len(f),
            "actual_resolution_steps": [str(x) for x in a_steps],
            "forecast_resolution_steps": f_step_set,
            "actual_span_utc": [a["startTime"].min().isoformat(), a["startTime"].max().isoformat()],
            "forecast_target_span_utc": [f["startTime"].min().isoformat(), f["startTime"].max().isoformat()],
            "forecast_publish_span_utc": [f["publishTime"].min().isoformat(), f["publishTime"].max().isoformat()],
            "lead_time_h": {
                "min": float(lead_h.min()),
                "max": float(lead_h.max()),
                "negative_lead_rows": int((lead_h < 0).sum()),
                "rows_at_or_above_12h": int((lead_h >= 12).sum()),
            },
            "distinct_publish_times": int(f["publishTime"].nunique()),
            "distinct_publish_times_per_day": pubs_per_day,
            "actual_periods_expected": len(expected),
            "actual_periods_missing": [t.isoformat() for t in missing],
            "actual_rows_per_day": coverage_per_day,
            "vintages_per_target": {
                "min": int(f.groupby("startTime").size().min()),
                "max": int(f.groupby("startTime").size().max()),
                "median": float(f.groupby("startTime").size().median()),
            },
        }
    )
    return a, f, report


def write_csv_gz(df: pd.DataFrame, path: Path) -> None:
    """Write gzip with mtime=0 so identical data gives byte-identical files.

    pandas' ``compression={"method": "gzip", "mtime": 0}`` does not actually
    suppress the timestamp here (verified: two writes of the same frame gave
    different digests), so the gzip member is built by hand.
    """
    csv_bytes = df.to_csv(index=False, lineterminator="\n").encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, filename="") as gz:
        gz.write(csv_bytes)
    path.write_bytes(buf.getvalue())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch even if a snapshot exists")
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if ACTUALS_PATH.exists() and FORECASTS_PATH.exists() and not args.force:
        print("snapshot already present; use --force to refetch")
        print(REPORT_PATH.read_text(encoding="utf-8") if REPORT_PATH.exists() else "")
        return 0

    print("fetching actuals (FUELHH, WIND)...")
    actuals_raw = fetch_actuals()
    print("fetching forecasts (WINDFOR)...")
    forecasts_raw = fetch_forecasts()

    actuals, forecasts, report = normalise(actuals_raw, forecasts_raw)

    write_csv_gz(actuals, ACTUALS_PATH)
    write_csv_gz(forecasts, FORECASTS_PATH)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"\nwrote {ACTUALS_PATH.name} ({ACTUALS_PATH.stat().st_size / 1024:.0f} KB), "
          f"{FORECASTS_PATH.name} ({FORECASTS_PATH.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
