# Headroom — walkthrough script

Two parts, ten minutes total. Written to be spoken, not read: short sentences,
contractions, no bullet-point voice. Say it in your own words — the numbers are
what need to be exact.

**Before you record**

- Open two browser windows: the live app, and the repo on GitHub.
- In the app, dismiss the "How to read this" panel so it does not cover the
  dashboard mid-demo.
- Have these tabs pre-loaded so you are never waiting on a load:
  - `/?tab=dashboard&start=2026-01-05&end=2026-01-11&mode=day_ahead`
  - `/?tab=replay&day=2026-01-12&cutoff=09%3A20`
  - `/?tab=plan&mode=day_ahead&start=2026-01-01&end=2026-01-31&confidence=0.9`
  - `/?tab=misses&mode=day_ahead`
- Terminal ready in `backend/` for the test run in Part 2.

---

# Part 1 — The client pitch (target 4:45)

## 0:00 — Hook

> [SHOW: Decision Replay, 12 January, parked on the 07:30 vintage]

"On the eleventh of January, at half past seven in the morning, this was the
wind forecast for one o'clock the following night. Twenty thousand, nine hundred
and forty-two megawatts.

The auction closed at twenty past nine. That forecast is what the desk bought
against.

The wind delivered fourteen thousand and forty-eight.

Just under seven gigawatts short, with seventeen hours' notice. Somebody bought
that gap at whatever the market was charging at one in the morning."

*(Pause. Let it sit.)*

## 0:40 — The problem

> [SHOW: Dashboard, 05–11 January, day-ahead mode]

"This is the problem in one line. You commit the day before. The wind arrives the
day after. In between is weather.

The white line is what the wind actually did. The dashed blue line is what the
forecast said — and importantly, only the forecast that had actually been
published before the gate closed. Not a later one. Not hindsight.

Across the whole of January the gap between those two lines averaged two thousand
one hundred and forty-five megawatts. Against average output of about eleven and
a half gigawatts.

So any plan built on the headline forecast number is out by roughly two gigawatts
on a typical day. The desk already knows the forecast is uncertain. What it
hasn't had is a number for it."

## 1:30 — Decision Replay

> [SHOW: Replay tab, 12 January. Press Play. Let it run through.]

"Here's what that twelfth of January looked like from the inside.

I'm dragging through every forecast that was published for that delivery day,
oldest to newest. Each one is what was on screen at that moment. The older ones
fade out behind.

> [SHOW: point at the amber gate marker]

That amber line is the auction closing. Everything to the left of it, you knew.
Everything to the right, you didn't — and notice the tool won't let you use it.

> [SHOW: drag the slider past delivery; the white actual draws in]

And the actual only appears as the slider passes each half hour, because that's
when you'd have found out. You can't accidentally cheat with this. You see what
the desk saw, when the desk saw it."

## 2:30 — Plan on X MW

> [SHOW: Plan tab, whole month, confidence 90%]

"So that's the problem. Here's the answer.

Instead of giving you a forecast, this gives you a number you can commit to. It
takes the forecast, then subtracts the error this forecast has actually made at
this notice period in the past — not a textbook distribution, its own track
record.

At ninety per cent confidence, across January, that number averaged eight
thousand six hundred and forty-four megawatts.

> [SHOW: point at the shortfall rate on the hero card — 11.5% at the gate]

And here's the part I'd want you to check. Wind came in under that plan eleven
and a half per cent of the time. We promised ten. So it ran about one and a half
points optimistic — and the card says so, in amber, rather than rounding it to
"about right".

Now, how solid is that one and a half points? Honestly, not very. January gives
us twenty-four scored days, and nineteen of them had no shortfall at all — the
whole number comes from three bad days. Resample those days and the ninety per
cent range runs from three per cent to twenty-one. That contains ten. So the
miss is within sampling noise, and I'd want a few more months before claiming
the method is genuinely optimistic.

And that's measured the hard way. The first week of January is thrown out,
because its bands had no earlier errors to learn from. Leave it in and this reads
ten point three per cent, which looks better and proves less.

> [SHOW: drag the confidence buttons 50 → 95]

Want more certainty? The number drops and you buy more. Fifty per cent gets you
about eleven point four gigawatts, but you're short more than half the time.
Ninety-five gets you just under eight gigawatts, short under nine per cent of
the time.
That's the trade, and it's yours to set, not ours."

## 3:30 — The cost slider

> [SHOW: cost ratio buttons, move 1× → 3× → 5×]

"One more. The right answer depends on what being wrong costs you, and being
short usually costs more than being long.

So you tell it the ratio. If a shortfall hurts three times as much as a surplus,
it stops using the middle of the range and moves to the quantile that actually
minimises your expected cost. Three times worse means planning on nine thousand
nine hundred and twenty-two megawatts, and being short about a quarter of the
time instead of half.

No statistics required at your end. One question: how much worse is short than
long?"

## 4:10 — Biggest misses and close

> [SHOW: Biggest misses tab]

"Finally, the month's ten worst periods. All ten were that same twelfth of
January.

> [SHOW: point at the 'size' tags]

And every one is tagged *size*, not *timing*. We test that: shift the forecast up
to three hours either way and see if the error collapses. It doesn't — about five
per cent. So the forecast had the shape of the day right and the level badly
wrong. Hedging for a mistimed front wouldn't have saved you. Hedging for a level
miss would.

> [SHOW: click a row → it opens Decision Replay for that day]

Any row drops you straight into the replay for that day.

So: **plan on nine thousand megawatts at ninety per cent confidence**, and buy
the rest. That's the whole product. Not a better forecast — an honest number for
how wrong the forecast usually is, in a form you can take into the auction."

---

# Part 2 — Tech lead review (target 4:45)

## 0:00 — Architecture

> [SHOW: a simple diagram — draw it or use the README folder guide. Four boxes
> left to right: **Elexon BMRS** → **ingest.py (one-off)** → **CSV.gz snapshot
> committed to the repo** → **FastAPI** → **React/Recharts**. Put a dashed box
> around the three pure modules — selection, metrics, bands — hanging off
> FastAPI, labelled "no framework imports, unit-testable".]

"Architecture is deliberately dull, which is the point.

Elexon is hit exactly once, by an ingest script, which writes a gzipped CSV
snapshot that's committed to the repo. A hundred kilobytes for the month. The API
reads that snapshot and never calls Elexon at request time — so there's no
runtime dependency on someone else's uptime, and the numbers can't quietly change
under a reviewer.

The domain logic — selection, metrics, bands, analysis — is pure functions over
pandas with no FastAPI imports anywhere. The API is a thin typed layer on top.
That's what makes the test suite possible."

## 0:50 — The core rule and leakage

> [SHOW: backend/app/selection.py, the select_live_forecasts docstring]

"The whole product rests on one definition. For a delivery period T and a cutoff
C, the live forecast is the one with the latest publishTime at or before C.
Anything published after C is never used for T.

That sounds trivial. It's the main risk in the entire build. Get it wrong by one
row and every accuracy number becomes optimistic, the bands become too narrow,
and the product confidently lies to a trading desk. You would not notice from the
charts — they'd just look good.

It's a single vectorised `merge_asof`, backward, exact matches allowed. The merge
*is* the rule: last row at or before the key.

> [SHOW: backend/tests/test_selection.py, test_never_uses_future_forecasts]

And this is how I know it holds. It's a Hypothesis property test. It generates
random forecast sets, random publish times including ties and publications after
delivery, random horizons from zero to seventy-two hours — and asserts two
things. The selected publishTime is always at or before the cutoff. And it's
always the latest one that qualifies, checked against a brute-force reference
that doesn't use merge_asof at all.

> [SHOW: terminal — `pytest -q` → 95 passed]

Ninety-six tests. That one is the one I'd point a reviewer at first."

## 2:00 — Walk-forward bands

> [SHOW: backend/app/bands.py, the walk_forward_bands docstring]

"The bands are empirical, not parametric. For a target in week k, the error
quantiles come from weeks strictly before k, in the same horizon bucket.

The trap here is subtle and it's the same family as leakage: if you fit the bands
on the whole month and then measure coverage on the whole month, you'll get a
beautiful calibration number that means nothing. So the test asserts on *source
timestamps* — it checks the latest target whose error fed each band predates that
band's own week. Not on the output, on the provenance.

Week zero has nothing earlier to learn from. It falls back to a pooled
distribution, and that fallback genuinely does use later data — there's no honest
alternative inside one month. So it's flagged `warm-up` and excluded from the
calibration figures, and the docstring says so in as many words.

> [SHOW: Plan tab calibration badge — 75.3%]

Result: the eighty per cent band actually covered seventy-five point three per
cent. Slightly under-covering. I'm reporting that rather than tuning until it
looks like eighty, because a band that lies about its own width is worse than no
band."

## 3:00 — Stack, tests, CI, deploy

> [SHOW: README folder guide, then the repo root]

"Quickly through the rest.

Backend is FastAPI with Pydantic response models — thirteen GET endpoints,
everything in megawatts and ISO UTC, 422s with messages that name the real date
range rather than a schema dump. Heavy work is cached per parameter set, and
bands are always computed over the whole month then sliced, so zooming the date
range never silently changes what a number means.

Frontend is React and Recharts, plain CSS, three runtime dependencies. All
control state lives in the URL, so any view is a shareable link — which is also
how the deep-link tests work.

CI runs ruff and pytest, eslint and a production build, on every push. Docker
compose brings the whole thing up on one command, backend non-root with a
healthcheck, nginx proxying the API same-origin. Vercel serves the static bundle
plus the same FastAPI app as a Python function — the entrypoint re-exports the
identical app object, so there's one copy of the application, not two."

## 4:00 — Trade-offs and next steps

> [SHOW: README limitations section]

"Trade-offs, honestly.

CSV.gz over Parquet, to avoid pulling pyarrow into a serverless bundle — about
a hundred and thirty megabytes installed against a two-fifty limit, so that
mattered.

Hourly forecasts held across both half-hours, so every settlement period is
scored. The cost is that adjacent halves share a forecast value, so my sample
sizes overstate independence. It's in the README.

And the big one. The forecast series runs about one point one six times the
metered actuals. Dividing by that single number removes forty-six and a half per
cent of the MAE and takes bias from plus eighteen hundred megawatts to roughly
zero. So about half of what looks like forecast error is a level difference.

I dug into why, and I'll be straight with you: it's mixed, and one month can't
settle it. There's a steady gap of under a gigawatt at every wind level, which
looks like the two datasets counting different wind farms. But there's also a
much bigger shortfall at high wind — metered output never got past seventeen
point eight gigawatts all month while the forecast reached twenty-one point two,
and the windiest forty per cent of periods account for seventy-two per cent of
the whole gap. That's what curtailment or a metering ceiling looks like.

I fitted both stories. A pure scalar leaves nine hundred and fifty megawatts of
residual; a pure cap leaves nine hundred and seventy-six. Neither wins. So the
app reports the offset and doesn't claim a cause, and the Data quality tab shows
the working. Getting curtailment data to separate the two is the first thing I'd
do next.

It doesn't affect the confidence numbers, because the bands learn whatever level
difference is in the history.

After that: twelve months instead of one, for seasonal bands. Real imbalance
prices, so the cost ratio becomes pounds instead of a ratio. And a persistence
benchmark, so we can say whether this error level is actually good — right now I
can tell you what the error is, but not whether it's skilful.

That's Headroom."

---

## Timing check

| Segment | Target | Running |
|---|---|---|
| P1 hook | 0:40 | 0:40 |
| P1 problem | 0:50 | 1:30 |
| P1 replay | 1:00 | 2:30 |
| P1 plan | 1:00 | 3:30 |
| P1 cost | 0:40 | 4:10 |
| P1 misses + close | 0:35 | 4:45 |
| P2 architecture | 0:50 | 5:35 |
| P2 rule + test | 1:10 | 6:45 |
| P2 bands | 1:00 | 7:45 |
| P2 stack | 1:00 | 8:45 |
| P2 trade-offs | 0:45 | 9:30 |

Thirty seconds of slack. If you run long, cut the cost slider section in Part 1
to one sentence — the confidence slider already makes the point.

## Numbers to get exactly right

- Forecast **20,942 MW**, actual **14,048 MW**, miss **6,894 MW**, 12 Jan 01:00,
  17.5 hours of lead
- Month MAE at the 09:20 gate: **2,145 MW**, mean output **11,581 MW**
- Plan at 90%: **8,644 MW**, realised shortfall **11.5%** (walk-forward, 1,152
  periods; 10.3% if the warm-up week is left in)
- Shortfall 90% interval **3.0–21.4%**, block bootstrap over days — contains 10%,
  so **within sampling noise**; **19 of 24 days** had no shortfall at all
- Cost ratio 3×: plan **9,922 MW**, short **24.2%** of periods
- Calibration: 80% band covered **75.3%**
- 15:30 gate is **160 MW (7.5%)** better than 09:20; 09:50 only **19 MW** better
- **96** tests
- Scope offset: ratio **1.16**, scalar removes **46.5%** of MAE (2,061 → 1,102 MW
  at the 24 h horizon, the app's default view); bias **+1,849 → −6 MW**
- Offset is **mixed**: steady sub-GW gap at all levels, plus high-wind
  saturation — actual peaked at **17.8 GW**, forecast reached **21.2 GW**, and the
  windiest **40%** of periods carry **72%** of the gap; scalar residual **950 MW**
  vs cap residual **976 MW**
