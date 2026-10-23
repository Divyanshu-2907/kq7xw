"""Configuration constants and env overrides.

Pure constants only: no FastAPI, no I/O at import time beyond reading env vars.
"""

from __future__ import annotations

import os
from datetime import time

LONDON_TZ = "Europe/London"

# --- Day-ahead cutoff -------------------------------------------------------
# Default = 09:20 Europe/London, the order-book closure of the GB 60-minute
# day-ahead auction on EPEX SPOT, held the day before delivery (results from
# 09:30). It moved to 09:20 from 11:00 in 2020 ahead of GB leaving the
# EU day-ahead coupling.
#   https://www.epexspot.com/sites/default/files/2024-12/_Trading%20brochure%202024%20December%20%281%29.pdf
# The other GB day-ahead auction, Nord Pool's N2EX hourly auction, has gate
# closure at 09:50 UK time (results by 10:00):
#   https://support.nordpoolgroup.com/support/solutions/articles/8000088463-about-the-n2ex-day-ahead-auction
# EPEX also runs a GB 30-minute day-ahead auction closing 15:30 the day before.
# We default to the EARLIEST of the hourly gates (09:20) because a plan that is
# safe at the earliest gate is safe at the later ones; a desk that only trades
# N2EX can set 09:50, and 15:30 models the half-hourly auction.
# Both times are quoted as UK clock time, so we apply them in Europe/London.
DEFAULT_DAY_AHEAD_CUTOFF_LOCAL: time = time.fromisoformat(
    os.getenv("HEADROOM_DAY_AHEAD_CUTOFF_LOCAL", "09:20")
)

# --- Forecast/actual time-grid alignment ------------------------------------
# WINDFOR is published on an hourly grid; FUELHH actuals are half-hourly.
# One switch, two options (see selection.align_forecast_grid docstring):
#   "hold"          -> an hourly forecast covers both half-hours of its hour
#   "hourly_points" -> only compare at exact hour starts
FORECAST_ALIGNMENT: str = os.getenv("HEADROOM_FORECAST_ALIGNMENT", "hold")
