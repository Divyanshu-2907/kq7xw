# Project: Headroom
"Know how much wind you can count on before the day-ahead auction closes."

## Who it's for
A UK energy utility's day-ahead trading team. Every day they decide, the day before delivery, how much power to buy beyond what wind will supply. They need to (1) see the latest wind forecast available at decision time and (2) know quantitatively how wrong those forecasts tend to be, so they can buy with the error in mind.

## Hard scope limits (from the client brief)
- Data: ONLY Elexon BMRS national wind data. Actuals = FUELHH (fuelType = WIND). Forecasts = WINDFOR (startTime, publishTime, generation). No weather, demand or price data.
- Period: target (delivery) times in January 2026. Forecasts published in late December 2025 are needed for early-January targets.
- Stack: React frontend, Python FastAPI backend, Docker, deploy on Vercel. Public GitHub repo with an anonymous name.
- 16-hour total effort budget. Prefer finished and correct over ambitious and broken.

## The core rule (everything depends on this)
For a target time T and a decision cutoff C, the "live" forecast is the one with the latest publishTime <= C among forecasts for T. Two modes:
- Horizon mode: C = T - H hours (H is chosen by the user).
- Day-ahead mode: C = a fixed clock time on the day before T's delivery day (default configurable, Europe/London time).
A forecast published after C must NEVER be used for T. This is the leakage risk the whole app must be safe against.

## Product features
Required:
1. Dashboard: actual vs live forecast over time in MW, for a chosen date range and horizon/mode.
2. Accuracy metrics: MAE, RMSE, bias, and MAE as % of mean actual generation (NOT MAPE, because MAPE explodes near zero wind; explain this in the UI tooltip).
3. Historical explorer: click any target time to see every forecast ever published for it (publishTime, lead time, MW), which one was live at the cutoff, and the actual.
Signature (what makes this unique):
4. Decision Replay: pick a delivery day, drag a publish-time slider, and see the forecast for that day exactly as it stood at that moment, with older vintages fading behind it. The cutoff is a vertical line. The actual is only revealed once the slider passes delivery.
5. "Plan on X MW": empirical uncertainty bands around the forecast from historical errors by horizon, calibrated WALK-FORWARD (each week's bands use only earlier errors). A confidence slider gives one "wind you can count on" number per period.
6. Cost-aware buying: user sets how much worse a shortfall is than a surplus (ratio r). The app uses the newsvendor quantile q = r / (1 + r) of the predictive distribution instead of the median, and shows how the plan changes.
7. Biggest misses: top 10 worst periods, each one clickable into Decision Replay. For each, split the error into timing error (does shifting the forecast by +/-1..3h collapse the error?) vs size error.
8. Error analysis views: error vs horizon ("value of waiting"), error by hour of day, error by forecast wind level.
9. Data quality panel: coverage per day, missing intervals, duplicates, and how each was handled.

## Engineering rules
- Data is fetched once by an ingest script and committed as a compressed snapshot (CSV.gz, not Parquet, to keep the Vercel bundle small; avoid pyarrow). The API reads the snapshot; it never calls Elexon at request time.
- All timestamps are timezone-aware UTC internally. Convert to Europe/London only for the day-ahead cutoff and display.
- Domain logic (selection, metrics, bands) lives in pure functions with no FastAPI imports, so it's unit-testable.
- Typed API with Pydantic response models.
- Tests with pytest, including a property-based no-lookahead test with hypothesis.
- Never invent API parameter names, numbers or findings. If unsure, probe the real API or the real data and report what you found.
- Git: small commits with plain conventional messages (feat:, fix:, test:, docs:). Do NOT add Co-Authored-By lines, "Generated with" lines, or any AI attribution to commits or PRs.
- README must honestly state that AI tools (Claude Code) were used in development, because the client brief requires it.

## Folder structure
backend/
  app/        main.py, config.py, data.py, selection.py, metrics.py, bands.py, analysis.py, schemas.py
  scripts/    ingest.py
  data/       snapshot files
  tests/
  Dockerfile, requirements.txt
frontend/
  src/        App.jsx, api.js, components/, pages/, lib/
  Dockerfile
api/          Vercel Python entrypoint
docker-compose.yml, vercel.json, README.md, .github/workflows/ci.yml

## Working style
Work in phases. At the end of each phase: run the tests, summarise what changed and what you verified, list anything you were unsure about, then STOP and wait for my next message.
