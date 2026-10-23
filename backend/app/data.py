"""Load the committed snapshot. No network calls, ever, at request time.

The snapshot is produced once by ``backend/scripts/ingest.py`` and committed.
Loads are cached for the process lifetime: the files are small (~100 KB gzip)
and immutable, so there is nothing to invalidate.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ACTUALS_PATH = DATA_DIR / "actuals.csv.gz"
FORECASTS_PATH = DATA_DIR / "forecasts.csv.gz"
REPORT_PATH = DATA_DIR / "ingest_report.json"


@lru_cache(maxsize=1)
def load_actuals() -> pd.DataFrame:
    """FUELHH WIND actuals: ``startTime`` (UTC, half-hourly), ``generation`` MW."""
    df = pd.read_csv(ACTUALS_PATH)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["settlementPeriod"] = df["settlementPeriod"].astype("int16")
    df["generation"] = df["generation"].astype("float64")
    return df.sort_values("startTime", kind="mergesort").reset_index(drop=True)


@lru_cache(maxsize=1)
def load_forecasts() -> pd.DataFrame:
    """WINDFOR vintages: ``startTime``, ``publishTime`` (UTC, hourly), ``generation`` MW."""
    df = pd.read_csv(FORECASTS_PATH)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df["generation"] = df["generation"].astype("float64")
    return df.sort_values(["startTime", "publishTime"], kind="mergesort").reset_index(
        drop=True
    )


@lru_cache(maxsize=1)
def load_ingest_report() -> dict:
    """The provenance/quality record written by the ingest script."""
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def clear_cache() -> None:
    """Drop cached frames (tests, or after a re-ingest in the same process)."""
    load_actuals.cache_clear()
    load_forecasts.cache_clear()
    load_ingest_report.cache_clear()
