"""Pydantic response models. Units are MW; timestamps are ISO-8601 UTC with a Z.

Every float here is nullable on purpose: a target period with no eligible
forecast, or a metric over an empty sample, comes back as ``null`` with a
reason rather than as a zero that would quietly poison an average downstream.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

UtcDatetime = Annotated[
    datetime,
    PlainSerializer(
        lambda dt: dt.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        return_type=str,
    ),
]

Mode = Literal["horizon", "day_ahead"]


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# meta / health
# --------------------------------------------------------------------------- #
class Health(Base):
    status: Literal["ok"]
    snapshot_loaded: bool
    actual_rows: int
    forecast_rows: int


class HorizonRange(Base):
    min_h: float = Field(description="Smallest selectable horizon, in hours.")
    max_h: float = Field(
        description="Largest horizon with full coverage of the target month."
    )
    max_lead_in_data_h: float = Field(
        description="Longest lead time any publication offers. Horizons beyond "
        "max_h still work but cover fewer periods; coverage_pct says how many."
    )


class Meta(Base):
    target_start: UtcDatetime
    target_end: UtcDatetime = Field(description="Exclusive upper bound.")
    horizon: HorizonRange
    default_day_ahead_cutoff_local: str = Field(
        description="Europe/London clock time, HH:MM."
    )
    day_ahead_cutoff_note: str
    actual_resolution: str
    forecast_resolution: str
    alignment: str
    resolution_note: str
    publish_times_utc: list[str] = Field(
        description="Distinct publication clock times seen in the snapshot."
    )
    error_convention: str


# --------------------------------------------------------------------------- #
# series / metrics
# --------------------------------------------------------------------------- #
class SeriesPoint(Base):
    start_time: UtcDatetime
    cutoff: UtcDatetime
    publish_time: UtcDatetime | None
    lead_h: float | None
    forecast_mw: float | None
    actual_mw: float | None
    error_mw: float | None = Field(
        default=None, description="forecast - actual; positive means over-forecast."
    )
    p10_mw: float | None = None
    p25_mw: float | None = None
    p50_mw: float | None = None
    p75_mw: float | None = None
    p90_mw: float | None = None
    band_basis: str | None = Field(
        default=None,
        description='"walk-forward", "pooled-prior", or "warm-up" (the first week, '
        "whose bands borrow from the whole sample and are therefore optimistic).",
    )
    reason: str


class Metrics(Base):
    count: int
    coverage_pct: float
    mae_mw: float | None
    rmse_mw: float | None
    bias_mw: float | None = Field(
        default=None, description="Positive means the forecast ran high."
    )
    nmae_pct: float | None = Field(
        default=None,
        description="MAE as a percentage of mean actual generation. Used instead "
        "of MAPE, which explodes when wind output nears zero.",
    )
    p50_abs_error_mw: float | None
    p90_abs_error_mw: float | None
    mean_actual_mw: float | None


class Selection(Base):
    """Echo of how the live forecast was chosen, so a chart can caption itself."""

    mode: Mode
    horizon_h: float | None
    cutoff_local_time: str | None
    alignment: str
    start: UtcDatetime
    end: UtcDatetime


class SeriesResponse(Base):
    selection: Selection
    metrics: Metrics
    points: list[SeriesPoint]


class MetricsResponse(Base):
    selection: Selection
    metrics: Metrics


# --------------------------------------------------------------------------- #
# error breakdowns
# --------------------------------------------------------------------------- #
class HorizonRow(Metrics):
    horizon_h: float
    mean_lead_h: float | None


class HourRow(Metrics):
    hour: int = Field(description="Hour of the delivery period, Europe/London.")


class LevelRow(Metrics):
    wind_level: str = Field(description="Forecast MW bucket, left-closed.")


class ErrorByHorizonResponse(Base):
    rows: list[HorizonRow]
    note: str


class ErrorByHourResponse(Base):
    selection: Selection
    rows: list[HourRow]


class ErrorByLevelResponse(Base):
    selection: Selection
    rows: list[LevelRow]
    note: str


# --------------------------------------------------------------------------- #
# bands / plan
# --------------------------------------------------------------------------- #
class CalibrationRow(Base):
    interval: str
    nominal_pct: float
    empirical_pct: float | None
    n: int
    miss_low_pct: float | None
    miss_high_pct: float | None


class CalibrationResponse(Base):
    selection: Selection
    rows: list[CalibrationRow]
    warmup_excluded: bool
    note: str


class PlanPoint(Base):
    start_time: UtcDatetime
    lead_h: float | None
    forecast_mw: float | None
    actual_mw: float | None
    plan_mw: float | None = Field(
        description="Wind you can count on for this period at the chosen "
        "confidence, or at the cost-implied quantile."
    )
    median_plan_mw: float | None = None
    shift_vs_median_mw: float | None = None
    band_basis: str | None = None


class PlanTotals(Base):
    periods: int
    mean_forecast_mw: float | None
    mean_plan_mw: float | None
    mean_actual_mw: float | None
    plan_vs_forecast_mw: float | None = Field(
        default=None, description="How much wind the plan gives up against the forecast."
    )
    shortfall_rate_pct: float | None = Field(
        default=None, description="Share of periods where actual fell below plan."
    )
    mean_shortfall_mw: float | None
    worst_shortfall_mw: float | None
    mean_headroom_left_on_table_mw: float | None


class PlanResponse(Base):
    selection: Selection
    confidence: float | None
    cost_ratio: float | None
    newsvendor_q: float | None = Field(
        default=None, description="q = r / (1 + r), the quantile of demand to cover."
    )
    wind_quantile: float | None = Field(
        default=None, description="1 - q: the wind quantile the plan sits at."
    )
    totals: PlanTotals
    points: list[PlanPoint]


# --------------------------------------------------------------------------- #
# replay / slot
# --------------------------------------------------------------------------- #
class VintagePoint(Base):
    start_time: UtcDatetime
    forecast_mw: float


class Vintage(Base):
    publish_time: UtcDatetime
    eligible_at_cutoff: bool
    is_live: bool = Field(
        description="The one vintage the core rule selects at the cutoff."
    )
    points: list[VintagePoint]


class ActualPoint(Base):
    start_time: UtcDatetime
    actual_mw: float


class ReplayResponse(Base):
    day: str
    delivery_start: UtcDatetime
    delivery_end: UtcDatetime
    cutoff: UtcDatetime = Field(
        description="Decision gate for this delivery day; vintages published "
        "after it were not available when the buy was made."
    )
    cutoff_local_time: str
    publish_times: list[UtcDatetime] = Field(
        description="Slider positions, oldest first."
    )
    vintages: list[Vintage]
    actuals: list[ActualPoint]


class SlotForecast(Base):
    publish_time: UtcDatetime
    lead_h: float
    forecast_mw: float
    eligible_at_cutoff: bool
    is_live: bool


class SlotResponse(Base):
    start_time: UtcDatetime
    cutoff: UtcDatetime
    selection: Selection
    actual_mw: float | None
    live_forecast_mw: float | None
    live_publish_time: UtcDatetime | None
    error_mw: float | None
    forecasts: list[SlotForecast]


# --------------------------------------------------------------------------- #
# misses / data quality
# --------------------------------------------------------------------------- #
class Miss(Base):
    rank: int
    start_time: UtcDatetime
    publish_time: UtcDatetime | None
    lead_h: float | None
    forecast_mw: float
    actual_mw: float
    error_mw: float
    abs_error_mw: float
    miss_type: Literal["timing", "size", "unknown"]
    best_shift_h: float | None
    window_mae_unshifted_mw: float | None
    window_mae_at_best_shift_mw: float | None
    error_removed_by_shift_pct: float | None
    shift_curve_mw: dict[str, float] = Field(
        description="Window MAE for each candidate shift, keyed by hours."
    )
    decomposition_note: str | None


class MissesResponse(Base):
    selection: Selection
    rows: list[Miss]
    note: str


class CoverageDay(Base):
    date: str
    periods: int
    coverage_pct: float
    mean_mw: float
    min_mw: float
    max_mw: float


class DataQualityResponse(Base):
    model_config = ConfigDict(extra="allow")

    actual_rows: int
    actual_periods_expected: int
    actual_coverage_pct: float
    actual_periods_missing: list[UtcDatetime]
    actual_duplicate_start_times: int
    forecast_rows: int
    forecast_duplicate_keys: int
    forecast_negative_lead_rows: int
    forecast_lead_h_min: float
    forecast_lead_h_max: float
    distinct_publish_times: int
    publish_clock_times: dict[str, int]
    days_with_unusual_publish_count: dict[str, int]
    actual_mw_min: float
    actual_mw_max: float
    actual_zero_or_negative_periods: int
    coverage_per_day: list[CoverageDay]
    handling: dict[str, str]
    ingest: dict
