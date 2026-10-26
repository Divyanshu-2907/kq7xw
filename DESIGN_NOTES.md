# Design notes

The ten decisions most worth questioning, with the short answer to each. Written
to be said out loud, so the answers are two or three sentences rather than
essays. Numbers are from the committed January 2026 snapshot.

---

### 1. What exactly is the selection rule, and why is it the centre of the project?

For a delivery period T and a cutoff C, the live forecast is the one with the
latest `publishTime` at or before C — nothing published after C is ever used for
T. It is a single backward `merge_asof`, because that operation *is* the rule:
take the last row at or before the key. Everything else in the app is a
statistic computed on top of that selection, so if the rule is wrong, every
number is wrong together.

### 2. How do you know there is no lookahead?

A Hypothesis property test, `test_never_uses_future_forecasts`. It generates
random forecast sets, random publish times including ties and publications after
delivery, and random horizons from 0 to 72 hours, then asserts the selected
publish time is always at or before the cutoff and is always the latest one that
qualifies — checked against a brute-force reference that does not use
`merge_asof`. It also covers the awkward edges: publication exactly at the
cutoff, one second late, and day-ahead cutoffs across the London midnight
boundary.

### 3. You still shipped a leakage bug. What happened?

Yes, and it is the most useful thing in the repo. The bands are walk-forward —
week *k* uses only errors from earlier weeks — but week one has no history, so it
falls back to a distribution pooled over the whole month and is flagged
`warm-up`. `/api/calibration` excluded those rows; `/api/plan` did not, so the
headline shortfall rate was being measured partly on periods whose bands had seen
the answer. It read 10.3% against a 10% target, suspiciously perfect; excluding
the warm-up week it is 11.5%. There is now a test asserting the plan's
walk-forward sample is exactly the sample calibration reports, so the two cannot
drift apart silently again.

### 4. Why nMAE and not MAPE?

Because wind output goes near zero often enough that a per-period percentage
error explodes — a 200 MW miss on a 50 MW half-hour reads as 400% and would
dominate any average. nMAE divides MAE by the mean actual generation of the
sample instead, which is stable and still answers "how big is the error relative
to the wind we normally get". It is 17.8% at the default view, against a 2,061 MW
MAE on 11,581 MW of average output.

### 5. The forecast runs 1.16× the actuals. Is that not just a bad forecast?

No, and I can show it is not. Take the last forecast published for each period —
on average about 14 hours *after* delivery has already happened — and it is still
high by roughly the same amount, which no forecast error can explain. Dividing by
a single scalar removes 46.5% of MAE and takes bias from +1,849 MW to −6 MW, so
about half of the apparent error is a level difference rather than uncertainty.

### 6. So what causes it?

It is mixed, and one month cannot settle it. There is a persistent 0.6–1.0 GW gap
at every wind level, which looks like the two datasets covering different sets of
wind farms; but the gap grows sharply at high wind, where metered output
saturates near 17.8 GW while the forecast runs to 21.2 GW, and periods
forecasting above 16 GW are 40% of the sample yet carry 72% of the total gap.
A pure scalar and a pure cap fit about equally well (950 vs 976 MW mean absolute
residual), so the app reports the offset and declines to name a cause.

### 7. How are the uncertainty bands built, and are they honest?

Empirically, from the forecast's own track record: for a target in week *k*, the
error quantiles come from weeks strictly before *k* within the same horizon
bucket, and since `error = forecast − actual`, the low end of the predicted
actual comes from the high end of the error distribution. The test asserts on
*source timestamps* — that the latest target feeding each band predates that
band's own week — so it checks provenance, not just output. The 80% band covered
83.1% at the default view, which I report rather than tuning until it reads 80.

### 8. Your shortfall rate is 8.5%. How precisely do you know that?

Not very, and the tooltip says so. Half-hours within a day miss together —
19 of the 24 scored days had no shortfall at all, and three days carry nearly the
whole number — so a bootstrap that resamples individual periods would report
10.0–13.0% and be badly overconfident. Resampling whole days gives a 90% interval
of 2.1–15.7%, which contains the 10% target, so the gap from target is within
sampling noise on one month of data.

### 9. Why the newsvendor quantile rather than the median?

Because being short usually costs more than being long, and the median only
answers the symmetric question. With a shortfall-to-surplus ratio *r*, the
critical fractile is `q = r/(1+r)` of the demand you must cover; wind is
subtracted from that demand, so the matching wind quantile is `1 − q` — the more
you fear a shortfall, the lower the wind figure you plan on. At r = 3 the plan
moves to the 25th percentile of wind, 9.81 GW, and the realised shortfall rate
falls from 53% to about 21%.

### 10. Why hold the hourly forecast across both half-hours?

WINDFOR is hourly and FUELHH is half-hourly, so something has to give. Holding
the hourly value across both half-hours scores every settlement period, which is
the grid the desk actually settles on; the alternative, comparing only at exact
hours, is statistically cleaner but discards half the actuals. The cost is that
adjacent half-hours share a forecast value and their errors are correlated, so
quoted sample sizes overstate independence — it is one config switch, and the
README says so.

### 11. Why a committed snapshot instead of calling Elexon live?

Three reasons. The numbers cannot shift under a reviewer mid-assessment; there is
no runtime dependency on someone else's uptime or rate limits; and the whole
month is 100 KB of gzipped CSV, so it ships inside the serverless function with
room to spare. CSV rather than Parquet specifically to avoid pulling pyarrow into
a 250 MB bundle — the dependencies come to about 130 MB as it is.

### 12. What would you build next?

Twelve months instead of one, because the shortfall interval is too wide to prove
calibration on January alone. Then conditional bands for high-wind days, since
that is where the error concentrates and a single band per horizon is too blunt
for it. After that, curtailment or capacity data to settle the offset question,
and a persistence benchmark — right now I can tell you what the error is, but not
whether it is skilful.
