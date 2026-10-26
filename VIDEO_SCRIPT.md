# Headroom — walkthrough script

Two parts, ten minutes. Written to be spoken: short sentences, contractions, no
bullet-point voice. Say it your way — the numbers are what must be exact.

**Every number below is what the app shows at its default view** (Dashboard,
Horizon mode, 24 h, 1–31 January) unless the cue says otherwise. If you record
before pushing the latest commits, the live site will not match — push first.

---

## Demo click path

Set this up once, before recording. Open each in its own tab so you never hunt.

| # | When | Tab / URL | What to do |
|---|---|---|---|
| 1 | Hook | `/?tab=replay&day=2026-01-12` | Leave the slider where it lands — on the 07:30 vintage, labelled *the vintage the gate locked in*. The narrative line reads **20,942 MW**. |
| 2 | Problem | `/` (default) | Dashboard, whole month, Horizon 24 h. Point at the two lines, then the MAE card. |
| 3 | Replay | back to tab 1 | Press **Play**. Let it run ~5 s, then drag past delivery so the white actual draws in. |
| 4 | Plan | `/?tab=plan` | Hero card, then click **50%**, then **95%**, then back to **90%**. |
| 5 | Cost | same tab | Click **3×**. Watch the amber dotted line drop. |
| 6 | Misses | `/?tab=misses` | Point at the *size* tags, then click row 1 — it lands in Replay. |
| 7 | Part 2 | `/api/docs`, then the repo | Keep a terminal in `backend/` ready for `pytest -q`. |

Dismiss the how-to popover once before you start, or it covers the cards.

---

# Part 1 — The client pitch

## 0:00 Hook

> [SHOW: tab 1, Decision Replay, 12 January]

"On the eleventh of January, half past seven in the morning, this was the wind
forecast for one o'clock the following night. Twenty thousand, nine hundred and
forty-two megawatts.

The auction closed at twenty past nine. That's the forecast the desk bought
against.

The wind delivered fourteen thousand and forty-eight.

Just under seven gigawatts short, with seventeen hours' notice. Somebody bought
that gap at one in the morning, at whatever the market was charging."

## 0:35 The problem

> [SHOW: tab 2, Dashboard]

"That's the job in one line. You commit the day before. The wind arrives the day
after. In between is weather.

White line is what the wind did. Dashed blue is what the forecast said — and only
forecasts published before the gate closed. No hindsight.

Across January the average gap was two thousand and sixty-one megawatts, against
average output of about eleven and a half gigawatts. So any plan built on the
headline forecast is out by roughly two gigawatts on a normal day."

## 1:15 Decision Replay

> [SHOW: tab 1 again, press Play]

"Here's that twelfth of January from the inside. I'm moving through every
forecast published for that delivery day. Each one is what was on screen at that
moment. Older ones fade behind.

> [SHOW: point at the amber gate marker]

That amber line is the auction closing. Left of it you knew. Right of it you
didn't — and the tool won't let you use it.

> [SHOW: drag past delivery, the actual draws in]

The actual only appears as the slider passes each half hour, because that's when
you'd have found out. You can't cheat with this."

## 2:05 Plan on X MW

> [SHOW: tab 4, Plan, hero card]

"So that's the problem. Here's the answer.

Instead of a forecast, this gives you a number to commit to. The forecast, minus
the error it has actually made at this notice period — its own track record, not
a textbook.

At ninety per cent confidence, across January: eight point six one gigawatts.

> [SHOW: point at the 8.5% on the hero card]

Wind came in under that plan eight and a half per cent of the time. We promised
ten. So it was slightly conservative, which is the direction you'd want.

How solid is that? Honestly, not very — and the tool says so. Twenty-four scored
days, and nineteen had no shortfall at all. Three days carry nearly the whole
number. Resample by day and the range runs from two to nearly sixteen per cent.
That contains ten. So I can't yet prove the calibration is good to a point or
two. One month isn't enough, and I'd rather say so.

> [SHOW: click 50%, then 95%, back to 90%]

Want more certainty? The number drops and you buy more. Fifty per cent gives
eleven point four gigawatts, short more than half the time. Ninety-five gives
seven point nine, short seven per cent."

## 3:30 The cost slider

> [SHOW: click 3×]

"One more. The right answer depends on what being wrong costs you, and short
usually costs more than long.

So you set the ratio. If a shortfall hurts three times as much as a surplus, it
stops using the middle of the range and moves to the quantile that minimises
expected cost — nine point eight gigawatts, short about a fifth of the time
instead of half. One question at your end: how much worse is short than long?"

## 4:05 Biggest misses and close

> [SHOW: tab 6, Biggest misses]

"Finally, the month's worst periods. They cluster — the ten worst fall on two
days.

> [SHOW: point at the size tags]

Every one is tagged *size*, not *timing*. We test that: shift the forecast up to
three hours either way and see if the error collapses. It doesn't. So the
forecast had the shape of the day right and the level wrong. Hedging a mistimed
front wouldn't have saved you.

> [SHOW: click row 1 — it opens Decision Replay]

Any row drops into the replay for that day.

So: plan on eight point six gigawatts at ninety per cent, buy the rest, and know
the uncertainty on that promise. Not a better forecast — an honest number for how
wrong the forecast usually is."

---

# Part 2 — Tech lead review

## 0:00 Architecture

> [SHOW: a diagram, or the README folder guide. Four boxes left to right:
> **Elexon BMRS** → **ingest.py, run once** → **CSV.gz snapshot in the repo** →
> **FastAPI** → **React/Recharts**. Dashed box round selection, metrics and
> bands: "pure functions, no framework imports".]

"Architecture is deliberately dull. Elexon is hit once, by an ingest script that
writes a gzipped CSV into the repo — a hundred kilobytes. The API reads that and
never calls Elexon at request time, so there's no runtime dependency on someone
else's uptime and the numbers can't shift under a reviewer.

Selection, metrics and bands are pure functions over pandas, no FastAPI
imports. That's what makes the tests possible."

## 0:40 The core rule, and leakage

> [SHOW: backend/app/selection.py docstring]

"Everything rests on one definition. For a delivery period T and a cutoff C, the
live forecast is the one with the latest publish time at or before C. Anything
later is never used.

Sounds trivial. It's the main risk in the build. Get it wrong by one row and
every accuracy number is optimistic, the bands too narrow, and the product lies
to a trading desk — invisibly.

> [SHOW: test_never_uses_future_forecasts, then run pytest -q]

So it's a Hypothesis property test. Random forecast sets, random publish times
including ties and publications after delivery, random horizons. It asserts the
selected publish time is always at or before the cutoff, and always the latest
one that qualifies — against a brute-force reference that doesn't use merge_asof.

A hundred and eleven tests. That's the one I'd point you at first."

## 1:45 The leakage I shipped anyway

"Here's the part I'd want a reviewer to push on, because I got it wrong once.

Bands are walk-forward: week k uses earlier weeks only. Week one has no history,
so it borrows from the whole month. That's flagged, and calibration drops those
rows. The plan endpoint didn't.

So the headline shortfall rate was measured over periods whose bands had seen the
answer. It read ten point three per cent against a ten per cent target —
suspiciously perfect. Excluding the warm-up week it's eleven and a half.

Two endpoints describing the same thing on different samples. The fix is small;
the point is the test. There's now an assertion that the plan's walk-forward
sample is exactly the sample calibration reports, so they can't drift apart
silently again."

## 2:40 Bands, calibration and the bootstrap

> [SHOW: Plan tab calibration badge]

"Bands are empirical, not parametric. Error quantiles from earlier weeks, in the
same horizon bucket. The test asserts on source timestamps — that the latest
target feeding each band predates that band's own week. Provenance, not output.

The eighty per cent band covered eighty-three per cent. I report that rather than
tuning until it reads eighty.

And the shortfall rate gets an interval. Half-hours within a day miss together —
nineteen of twenty-four days had no shortfall at all. A naive bootstrap over
periods would say ten to thirteen per cent, which is badly overconfident.
Resampling whole days gives two to sixteen. That's the honest width."

## 3:30 Stack, and the dataset offset

"Quickly: FastAPI and Pydantic, thirteen endpoints, megawatts and ISO UTC
throughout. React and Recharts, three runtime dependencies, state in the URL so every view
is shareable. Ruff, pytest, eslint and a build on every push. Docker locally,
Vercel deployed, same app object in both.

One finding worth your time. The forecast series runs about one point one six
times the metered actuals, and dividing by that removes forty-six and a half per
cent of MAE. Why is mixed: a steady sub-gigawatt gap at every wind level, which
looks like different fleets, plus a much bigger shortfall at high wind, where
metered output tops out near seventeen point eight gigawatts while the forecast
reaches twenty-one point two. A scalar and a cap fit about equally well, so the
app reports the offset and doesn't name a cause."

## 4:15 What next

"What I'd do next, in order. Twelve months instead of one — the shortfall
interval is too wide to prove calibration on January alone. Conditional bands for
high-wind days, because that's where the error concentrates and one band per
horizon is too blunt. Curtailment data to settle the offset. And a persistence
benchmark, so I can say whether this error level is actually good — right now I
can say what it is, not whether it's skilful.

That's Headroom."

---

## Timing

At 140 words a minute.

| Part | Spoken words | Runs | Budget | Spare |
|---|---|---|---|---|
| Part 1 | 612 | 4:22 | 5:00 | 38 s |
| Part 2 | 650 | 4:39 | 5:00 | 21 s |
| Total | 1,262 | 9:01 | 10:00 | 59 s | If you run long, cut the cost-slider section
in Part 1 to one sentence — the confidence slider already makes the point.

---

## Numbers to get exactly right

All at the default view (Dashboard, Horizon 24 h, 1–31 January) unless noted.

| Number | Where it shows on screen |
|---|---|
| **20,942 MW** forecast, **14,048 MW** actual | Decision Replay, 12 Jan — narrative line under the chart |
| **17.5 h** notice, gate **09:20** | Replay timeline marker, "auction closes 09:20" |
| **2,061 MW** MAE | Dashboard, MAE card |
| **~11,581 MW** mean wind | Dashboard, nMAE card subline |
| **8.61 GW** plan, **8.5%** shortfall | Plan tab, hero card |
| **2.1–15.7%** interval, **1,152** periods | Hero card tooltip |
| **11.42 GW** / 53.4% at 50%, **7.89 GW** / 7.0% at 95% | Plan tab, confidence buttons |
| **9.81 GW**, ~20.7% short at 3× | Plan tab, cost buttons |
| **83.1%** for the 80% band | Plan tab, calibration badge |
| **two days**, all tagged *size* | Biggest misses tab |
| **1.16×**, **46.5%** of MAE | Dashboard note, and Data quality tab |
| **17.8 GW** actual peak vs **21.2 GW** forecast | Data quality tab |
| **19 of 24** days with no shortfall | Not on screen — from the analysis; quote as context |
| **111** tests | `pytest -q` in `backend/` |

Day-ahead gate figures, if you switch modes: plan **8.64 GW**, shortfall
**11.5%**, interval **3.0–21.4%**, warm-up-included reading **10.3%**.
