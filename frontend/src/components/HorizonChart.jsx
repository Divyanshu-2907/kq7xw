import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { MW, pct } from '../lib/format.js'

// How much accuracy you buy by deciding later. Each point is an independent
// no-lookahead run over the whole month, not a time series.

function HorizonTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="chart-tip">
      <div className="chart-tip-head">{d.horizon_h} h before delivery</div>
      <dl className="tip-grid">
        <dt>MAE</dt>
        <dd>{MW(d.mae_mw)}</dd>
        <dt>RMSE</dt>
        <dd>{MW(d.rmse_mw)}</dd>
        <dt>Coverage</dt>
        <dd>{pct(d.coverage_pct, 1)}</dd>
      </dl>
      {d.coverage_pct < 99.5 && (
        <div className="tip-foot">
          Fewer periods have any forecast this far out, so part of this is
          thinning coverage.
        </div>
      )}
    </div>
  )
}

export default function HorizonChart({ rows, currentHorizon, active, height = 212 }) {
  const here = rows.find((r) => r.horizon_h === currentHorizon)

  return (
    <div className="chart-wrap">
      <div className="legend">
        <span>
          <i className="swatch" style={{ background: 'var(--forecast)' }} /> MAE by horizon
        </span>
        {active && here && (
          <span style={{ color: 'var(--text-dim)' }}>
            at {currentHorizon} h: {MW(here.mae_mw)}
          </span>
        )}
        <span style={{ color: 'var(--text-faint)' }}>axis GW</span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={rows} margin={{ top: 6, right: 10, left: 2, bottom: 2 }}>
          <CartesianGrid strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="horizon_h"
            type="number"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(v) => `${v}h`}
            tickLine={false}
            minTickGap={16}
            stroke="var(--line)"
          />
          <YAxis
            tickFormatter={(v) => `${(v / 1000).toFixed(1)}`}
            width={30}
            tickLine={false}
            stroke="var(--line)"
            domain={[0, 'auto']}
          />
          <Tooltip content={<HorizonTooltip />} />
          {active && here && (
            <ReferenceLine
              x={currentHorizon}
              stroke="var(--text-faint)"
              strokeDasharray="3 3"
            />
          )}
          <Line
            dataKey="mae_mw"
            stroke="var(--forecast)"
            strokeWidth={1.6}
            dot={{ r: 2, fill: 'var(--forecast)', strokeWidth: 0 }}
            isAnimationActive={false}
          />
          {active && here && (
            <ReferenceDot
              x={here.horizon_h}
              y={here.mae_mw}
              r={4.5}
              fill="var(--forecast)"
              stroke="var(--panel)"
              strokeWidth={2}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
