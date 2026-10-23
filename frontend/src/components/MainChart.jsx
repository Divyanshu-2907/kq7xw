import { useMemo } from 'react'
import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Info } from './States.jsx'
import { MW, hours, signedMW, stampUTC, timeUTC } from '../lib/format.js'

// Actual against the forecast that was live at the cutoff, with the
// walk-forward P10-P90 band behind it. Brush to zoom.

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  return (
    <div className="chart-tip">
      <div className="chart-tip-head">{stampUTC(d.start_time)}</div>
      <dl className="tip-grid">
        <dt>Actual</dt>
        <dd>{MW(d.actual_mw)}</dd>
        <dt>Forecast</dt>
        <dd>{MW(d.forecast_mw)}</dd>
        <dt>Error</dt>
        <dd>{signedMW(d.error_mw)}</dd>
        {d.p10_mw != null && (
          <>
            <dt>P10–P90</dt>
            <dd>
              {MW(d.p10_mw)} – {MW(d.p90_mw)}
            </dd>
          </>
        )}
        <dt>Lead time</dt>
        <dd>{hours(d.lead_h)}</dd>
      </dl>
      <div className="tip-foot">
        Published {stampUTC(d.publish_time)}
        {d.band_basis === 'warm-up' && ' · band is warm-up, not walk-forward'}
        {d.reason !== 'ok' && ` · ${d.reason.replace(/_/g, ' ')}`}
      </div>
    </div>
  )
}

export default function MainChart({ points, height = 300, onPickSlot }) {
  const data = useMemo(
    () =>
      points.map((p) => ({
        ...p,
        t: new Date(p.start_time).getTime(),
        // Recharts draws a range Area from a [low, high] pair
        band: p.p10_mw != null && p.p90_mw != null ? [p.p10_mw, p.p90_mw] : null,
      })),
    [points],
  )

  const multiDay =
    data.length > 1 && data.at(-1).t - data[0].t > 36 * 3600 * 1000

  // One tick per midnight when the window spans days, so a week does not print
  // "05 Jan" six times; otherwise let Recharts pick time ticks.
  const ticks = useMemo(() => {
    if (!multiDay || !data.length) return undefined
    const out = []
    for (const d of data) if (new Date(d.t).getUTCHours() === 0 && new Date(d.t).getUTCMinutes() === 0) out.push(d.t)
    return out.length > 1 ? out : undefined
  }, [data, multiDay])

  return (
    <div className="chart-wrap">
      <div className="legend">
        <span>
          <i className="swatch" style={{ background: 'var(--actual)' }} /> Actual
        </span>
        <span>
          <i className="swatch" style={{ background: 'var(--forecast)' }} /> Live forecast
        </span>
        <span>
          <i className="swatch band" /> P10–P90 band{' '}
          <Info>
            Empirical uncertainty from this forecast&apos;s own past errors at
            this horizon, calibrated walk-forward: each week uses only errors
            from earlier weeks. Actual should land inside the band 80% of the time.
          </Info>
        </span>
        <span style={{ color: 'var(--text-faint)' }}>axis GW · values MW</span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart
          data={data}
          margin={{ top: 6, right: 8, left: 2, bottom: 0 }}
          onClick={(e) => {
            const t = e?.activePayload?.[0]?.payload?.start_time
            if (t && onPickSlot) onPickSlot(t)
          }}
          style={onPickSlot ? { cursor: 'pointer' } : undefined}
        >
          <CartesianGrid strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={['dataMin', 'dataMax']}
            ticks={ticks}
            tickFormatter={(t) =>
              multiDay
                ? new Intl.DateTimeFormat('en-GB', {
                    day: '2-digit', month: 'short', timeZone: 'UTC',
                  }).format(new Date(t))
                : timeUTC(new Date(t).toISOString())
            }
            minTickGap={24}
            tickLine={false}
            stroke="var(--line)"
          />
          <YAxis
            tickFormatter={(v) => `${(v / 1000).toFixed(0)}`}
            width={34}
            tickLine={false}
            stroke="var(--line)"
            domain={[0, 'auto']}
            allowDataOverflow
          />
          <Tooltip content={<ChartTooltip />} />
          <Area
            dataKey="band"
            stroke="none"
            fill="var(--band)"
            isAnimationActive={false}
            connectNulls={false}
            activeDot={false}
          />
          <Line
            dataKey="forecast_mw"
            stroke="var(--forecast)"
            strokeWidth={1.6}
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
          <Line
            dataKey="actual_mw"
            stroke="var(--actual)"
            strokeWidth={1.3}
            dot={false}
            isAnimationActive={false}
          />
          {data.length > 48 && (
            <Brush
              dataKey="t"
              height={22}
              travellerWidth={8}
              stroke="var(--line)"
              fill="var(--panel-2)"
              tickFormatter={() => ''}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
