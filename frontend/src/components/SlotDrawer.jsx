import { useEffect, useMemo } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api.js'
import { useEndpoint } from '../lib/useEndpoint.js'
import { MW, hours, signedMW, stampUTC } from '../lib/format.js'
import { ChartSkeleton, ErrorState } from './States.jsx'

// One delivery period, every forecast ever published for it. The x axis is
// publication time, so the line reads left to right as the forecast changing
// its mind on the approach to delivery.

function SlotTip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="chart-tip">
      <div className="chart-tip-head">{stampUTC(d.publish_time)}</div>
      <dl className="tip-grid">
        <dt>Forecast</dt>
        <dd>{MW(d.forecast_mw)}</dd>
        <dt>Lead</dt>
        <dd>{hours(d.lead_h)}</dd>
      </dl>
      <div className="tip-foot">
        {d.is_live
          ? 'this is the vintage the cutoff locked in'
          : d.eligible_at_cutoff
            ? 'was available at the cutoff'
            : 'published after the cutoff — never used'}
      </div>
    </div>
  )
}

export default function SlotDrawer({ time, params, onClose }) {
  const slot = useEndpoint(
    ({ signal }) => api.slot({ ...params, time }, { signal }),
    [time, JSON.stringify(params)],
    { enabled: Boolean(time) },
  )

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const d = slot.data
  const rows = useMemo(
    () =>
      (d?.forecasts ?? []).map((f) => ({
        ...f,
        t: new Date(f.publish_time).getTime(),
      })),
    [d],
  )
  const live = rows.find((r) => r.is_live)
  const cutoffMs = d ? new Date(d.cutoff).getTime() : null

  // Vintages for one period sit within a few hundred MW of each other, so a
  // zero-based axis would draw them as one flat line and hide the revisions
  // this view exists to show. The actual has to stay in frame too, since the
  // gap between it and the forecasts is the story.
  const domain = useMemo(() => {
    const values = rows.map((r) => r.forecast_mw).filter((v) => v != null)
    if (d?.actual_mw != null) values.push(d.actual_mw)
    if (!values.length) return [0, 'auto']
    const pad = Math.max(400, (Math.max(...values) - Math.min(...values)) * 0.15)
    return [Math.max(0, Math.min(...values) - pad), Math.max(...values) + pad]
  }, [rows, d])

  // Every hook above runs unconditionally; the early return comes after them.
  if (!time) return null

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-label="Forecast history for this period">
        <div className="drawer-head">
          <div>
            <div className="panel-title">Every forecast for this period</div>
            <div className="panel-note">{stampUTC(time)} delivery</div>
          </div>
          <button className="ghost-btn" onClick={onClose} type="button" aria-label="Close">
            ✕
          </button>
        </div>

        {slot.error ? (
          <ErrorState error={slot.error} onRetry={slot.retry} />
        ) : !d ? (
          /* `enabled` flips with `time`, so the first render after opening has
             neither data nor a loading flag yet: gate on the data itself. */
          <ChartSkeleton height={220} />
        ) : (
          <>
            <div className="drawer-stats">
              <div>
                <span className="control-label">Live forecast</span>
                <span className="num big">{MW(d.live_forecast_mw)}</span>
                <span className="panel-note">{stampUTC(d.live_publish_time)}</span>
              </div>
              <div>
                <span className="control-label">Actual</span>
                <span className="num big">{MW(d.actual_mw)}</span>
                <span className="panel-note">settled</span>
              </div>
              <div>
                <span className="control-label">Error</span>
                <span className={`num big ${d.error_mw > 0 ? 'over' : 'under'}`}>
                  {signedMW(d.error_mw)}
                </span>
                <span className="panel-note">
                  {d.error_mw > 0 ? 'forecast ran high' : 'forecast ran low'}
                </span>
              </div>
            </div>

            <div className="legend" style={{ marginTop: 10 }}>
              <span>
                <i className="swatch dashed" style={{ background: 'var(--forecast)' }} /> Forecast
                by publication (dashed)
              </span>
              <span>
                <i className="swatch" style={{ background: 'var(--actual)' }} /> Actual
              </span>
            </div>

            <ResponsiveContainer width="100%" height={230}>
              <ComposedChart data={rows} margin={{ top: 20, right: 12, left: 2, bottom: 2 }}>
                <CartesianGrid strokeDasharray="2 4" vertical={false} />
                <XAxis
                  dataKey="t"
                  type="number"
                  scale="time"
                  domain={['dataMin', 'dataMax']}
                  tickFormatter={(t) =>
                    new Intl.DateTimeFormat('en-GB', {
                      day: '2-digit', month: 'short', hour: '2-digit',
                      timeZone: 'UTC', hour12: false,
                    }).format(new Date(t))
                  }
                  minTickGap={46}
                  tickLine={false}
                  stroke="var(--line)"
                  fontSize={10}
                />
                <YAxis
                  tickFormatter={(v) => `${(v / 1000).toFixed(1)}`}
                  width={32}
                  tickLine={false}
                  stroke="var(--line)"
                  domain={domain}
                  allowDecimals={false}
                />
                <Tooltip content={<SlotTip />} />
                {d.actual_mw != null && (
                  <ReferenceLine
                    y={d.actual_mw}
                    stroke="var(--actual)"
                    strokeDasharray="4 3"
                    label={{
                      value: `actual ${Math.round(d.actual_mw).toLocaleString('en-GB')} MW`,
                      position: 'insideBottomRight',
                      fill: 'var(--text-dim)',
                      fontSize: 10,
                    }}
                  />
                )}
                {cutoffMs != null && (
                  <ReferenceLine
                    x={cutoffMs}
                    stroke="var(--warn)"
                    strokeDasharray="3 3"
                    label={{
                      value: 'cutoff',
                      position: 'top',
                      fill: 'var(--warn)',
                      fontSize: 10,
                    }}
                  />
                )}
                <Line
                  dataKey="forecast_mw"
                  stroke="var(--forecast)"
                  strokeWidth={1.6}
                  strokeDasharray="5 3"
                  dot={{ r: 2 }}
                  isAnimationActive={false}
                />
                {live && (
                  <ReferenceDot
                    x={live.t}
                    y={live.forecast_mw}
                    r={5}
                    fill="var(--forecast)"
                    stroke="var(--panel)"
                    strokeWidth={2}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>

            <p className="panel-note">
              {rows.length} publications, of which{' '}
              {rows.filter((r) => r.eligible_at_cutoff).length} were available at the
              cutoff. The ringed point is the one the rule selected; everything to
              the right of the dashed cutoff line was published too late to use.
            </p>
          </>
        )}
      </aside>
    </>
  )
}
