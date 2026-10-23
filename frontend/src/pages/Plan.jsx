import { useMemo } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api.js'
import { useEndpoint } from '../lib/useEndpoint.js'
import { MW, dayUTC, pct, stampUTC, timeUTC } from '../lib/format.js'
import { ChartSkeleton, ErrorState, Info } from '../components/States.jsx'

// "Plan on X MW": the number you can actually commit to, and what it costs you
// to be more careful.

const CONFIDENCES = [0.5, 0.8, 0.9, 0.95]
const RATIOS = [1, 2, 3, 5, 10]

// Half-hourly periods: MW held for half an hour is MWh/2.
const toMWh = (points, key) =>
  points.reduce((sum, p) => sum + Math.max(0, p[key] ?? 0) * 0.5, 0)

// At high confidence on a badly over-forecast period the quantile can land
// below zero. Negative wind is not something a desk can plan on, so it is shown
// and counted as zero -- "count on nothing here" -- rather than as a negative.
const floorAtZero = (v) => (v == null ? null : Math.max(0, v))

function PlanTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="chart-tip">
      <div className="chart-tip-head">{stampUTC(d.start_time)}</div>
      <dl className="tip-grid">
        <dt>Forecast</dt>
        <dd>{MW(d.forecast_mw)}</dd>
        <dt>Plan</dt>
        <dd>
          {MW(d.plan_mw)}
          {d.plan_raw_mw != null && d.plan_raw_mw < 0 ? ' *' : ''}
        </dd>
        <dt>Cost-aware</dt>
        <dd>{MW(d.cost_mw)}</dd>
        <dt>Actual</dt>
        <dd>{MW(d.actual_mw)}</dd>
      </dl>
      {d.plan_raw_mw != null && d.plan_raw_mw < 0 && (
        <div className="tip-foot">
          * the quantile landed below zero here, so the plan is nothing
        </div>
      )}
      {d.actual_mw != null && d.plan_mw != null && (
        <div className="tip-foot">
          {d.actual_mw < d.plan_mw
            ? `Short by ${MW(d.plan_mw - d.actual_mw)}`
            : `Covered, ${MW(d.actual_mw - d.plan_mw)} to spare`}
        </div>
      )}
    </div>
  )
}

export default function Plan({ params, confidence, costRatio, patch }) {
  const base = { ...params }
  const plan = useEndpoint(
    ({ signal }) => api.plan({ ...base, confidence }, { signal }),
    [JSON.stringify(base), confidence],
  )
  const cost = useEndpoint(
    ({ signal }) => api.plan({ ...base, cost_ratio: costRatio }, { signal }),
    [JSON.stringify(base), costRatio],
  )
  const cal = useEndpoint(
    ({ signal }) => api.calibration(base, { signal }),
    [JSON.stringify(base)],
  )

  const data = useMemo(() => {
    const rows = new Map()
    for (const p of plan.data?.points ?? []) {
      rows.set(p.start_time, {
        ...p,
        t: new Date(p.start_time).getTime(),
        plan_mw: floorAtZero(p.plan_mw),
        plan_raw_mw: p.plan_mw,
      })
    }
    for (const p of cost.data?.points ?? []) {
      const row = rows.get(p.start_time)
      if (row) row.cost_mw = floorAtZero(p.plan_mw)
    }
    return [...rows.values()].sort((a, b) => a.t - b.t)
  }, [plan.data, cost.data])

  const multiDay =
    data.length > 1 && data.at(-1).t - data[0].t > 36 * 3600 * 1000
  const ticks = useMemo(() => {
    if (!multiDay || !data.length) return undefined
    const out = data
      .filter((d) => {
        const dt = new Date(d.t)
        return dt.getUTCHours() === 0 && dt.getUTCMinutes() === 0
      })
      .map((d) => d.t)
    return out.length > 1 ? out : undefined
  }, [data, multiDay])

  const totals = plan.data?.totals
  const costTotals = cost.data?.totals
  const band = cal.data?.rows?.find((r) => r.interval === 'P10-P90')
  const gap = band?.empirical_pct != null ? band.empirical_pct - band.nominal_pct : null

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <span className="panel-title">Plan on X MW of wind</span>
          <span className="panel-note">
            per half-hourly period · from this forecast&apos;s own past errors
          </span>
          <Info>
            The plan is the forecast minus the error you have historically seen
            at this horizon, at the confidence you choose. Bands are calibrated
            walk-forward: each week uses only errors from earlier weeks.
          </Info>
        </div>

        <div className="plan-controls">
          <div className="control">
            <span className="control-label">
              Confidence{' '}
              <Info>
                &quot;Wind should be at least this much, this often.&quot; Higher
                confidence means a lower, safer number to plan on.
              </Info>
            </span>
            <div className="toggle">
              {CONFIDENCES.map((c) => (
                <button
                  key={c}
                  type="button"
                  aria-pressed={confidence === c}
                  onClick={() => patch({ confidence: c })}
                >
                  {Math.round(c * 100)}%
                </button>
              ))}
            </div>
          </div>

          <div className="control">
            <span className="control-label">
              A shortfall costs this many times more than a surplus{' '}
              <Info>
                Newsvendor rule: with ratio r the plan sits at quantile q = r/(1+r)
                of the demand you must cover, which is the (1 − q) quantile of
                wind. Fear being short more, plan on less wind.
              </Info>
            </span>
            <div className="toggle">
              {RATIOS.map((r) => (
                <button
                  key={r}
                  type="button"
                  aria-pressed={costRatio === r}
                  onClick={() => patch({ cost_ratio: r })}
                >
                  {r}×
                </button>
              ))}
            </div>
          </div>
        </div>

        {cal.data && band && (
          <div className={`badge ${gap != null && Math.abs(gap) > 5 ? 'warn' : 'ok'}`}>
            <strong>Calibration.</strong> Our {band.nominal_pct.toFixed(0)}% band
            actually covered <strong>{pct(band.empirical_pct)}</strong> of this
            selection ({band.n.toLocaleString('en-GB')} periods).{' '}
            {gap == null
              ? ''
              : Math.abs(gap) <= 5
                ? 'Close enough to trust at face value.'
                : gap > 0
                  ? `That is ${pct(gap)} wider than advertised — the plan is more cautious than the label suggests.`
                  : `That is ${pct(-gap)} short of the promise — the band is too narrow, so treat the plan as optimistic.`}
            {band.n < 300 && (
              <>
                {' '}
                <em>
                  On {band.n} periods this is a small sample — widen the date
                  range before reading much into it.
                </em>
              </>
            )}
          </div>
        )}

        {plan.loading && !plan.data ? (
          <ChartSkeleton height={300} />
        ) : plan.error ? (
          <ErrorState error={plan.error} onRetry={plan.retry} />
        ) : (
          <>
            <div className="legend">
              <span>
                <i className="swatch" style={{ background: 'var(--actual)' }} /> Actual
              </span>
              <span>
                <i className="swatch dashed" style={{ background: 'var(--forecast)' }} /> Forecast
                (dashed)
              </span>
              <span>
                <i className="swatch" style={{ background: 'var(--good)' }} /> Plan at{' '}
                {Math.round(confidence * 100)}%
              </span>
              <span>
                <i className="swatch dotted" style={{ background: 'var(--warn)' }} /> Cost-aware
                (dotted) at{' '}
                {costRatio}×
              </span>
              <span style={{ color: 'var(--text-faint)' }}>axis GW · values MW</span>
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={data} margin={{ top: 6, right: 10, left: 2, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 4" vertical={false} />
                <XAxis
                  dataKey="t"
                  type="number"
                  scale="time"
                  domain={['dataMin', 'dataMax']}
                  ticks={ticks}
                  tickFormatter={(t) =>
                    multiDay ? dayUTC(new Date(t).toISOString()) : timeUTC(new Date(t).toISOString())
                  }
                  minTickGap={34}
                  tickLine={false}
                  stroke="var(--line)"
                />
                <YAxis
                  tickFormatter={(v) => `${(v / 1000).toFixed(0)}`}
                  width={34}
                  tickLine={false}
                  stroke="var(--line)"
                  domain={[0, 'auto']}
                />
                <Tooltip content={<PlanTooltip />} />
                <Line dataKey="actual_mw" stroke="var(--actual)" strokeWidth={1.3}
                      dot={false} isAnimationActive={false} />
                <Line dataKey="forecast_mw" stroke="var(--forecast)" strokeWidth={1.4}
                      strokeDasharray="5 3" dot={false} isAnimationActive={false} />
                <Line dataKey="plan_mw" stroke="var(--good)" strokeWidth={2}
                      strokeDasharray="1 0" dot={false} isAnimationActive={false} />
                <Line dataKey="cost_mw" stroke="var(--warn)" strokeWidth={1.5}
                      strokeDasharray="4 3" dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </>
        )}
      </section>

      <div className="cards">
        <div className="card">
          <div className="card-label">
            Energy you can count on{' '}
            <Info>
              The plan line summed over the selection, at half an hour per
              period. This is the volume you could commit to without buying.
            </Info>
          </div>
          <div className="metric-value num">
            {(toMWh(data, 'plan_mw') / 1000).toFixed(1)}
            <span className="metric-unit">GWh</span>
          </div>
          <div className="metric-plain">
            at {Math.round(confidence * 100)}% confidence ·{' '}
            {MW(totals?.mean_plan_mw)} average
          </div>
        </div>
        <div className="card">
          <div className="card-label">Forecast energy</div>
          <div className="metric-value num">
            {(toMWh(data, 'forecast_mw') / 1000).toFixed(1)}
            <span className="metric-unit">GWh</span>
          </div>
          <div className="metric-plain">
            planning gives up {MW(Math.abs(totals?.plan_vs_forecast_mw))} per period
          </div>
        </div>
        <div className="card">
          <div className="card-label">
            Shortfall rate{' '}
            <Info>
              How often the actual came in below the plan. At 90% confidence you
              should expect roughly 10%.
            </Info>
          </div>
          <div className="metric-value num">{pct(totals?.shortfall_rate_pct)}</div>
          <div className="metric-plain">
            worst {MW(totals?.worst_shortfall_mw)} ·{' '}
            {MW(totals?.mean_shortfall_mw)} average when short
          </div>
        </div>
        <div className="card">
          <div className="card-label">
            Cost-aware plan at {costRatio}×{' '}
            <Info>
              Same data, but the quantile is chosen by how much worse a shortfall
              is than a surplus rather than by a confidence level.
            </Info>
          </div>
          <div className="metric-value num">
            {(toMWh(data, 'cost_mw') / 1000).toFixed(1)}
            <span className="metric-unit">GWh</span>
          </div>
          <div className="metric-plain">
            q = {cost.data?.newsvendor_q?.toFixed(3) ?? '—'} → wind quantile{' '}
            {cost.data?.wind_quantile?.toFixed(3) ?? '—'} · shortfall{' '}
            {pct(costTotals?.shortfall_rate_pct)}
          </div>
        </div>
      </div>
    </>
  )
}
