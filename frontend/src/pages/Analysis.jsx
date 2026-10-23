import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api.js'
import { useEndpoint } from '../lib/useEndpoint.js'
import { MW, pct, signedMW, windBand } from '../lib/format.js'
import { ChartSkeleton, ErrorState, Info } from '../components/States.jsx'

// Where the error actually comes from. Each takeaway below is written from the
// numbers in the response, not typed in by hand, so it cannot drift from them.

function Tip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="chart-tip">
      <div className="chart-tip-head">
        {unit === 'hour' ? `${String(label).padStart(2, '0')}:00 London` : windBand(d.wind_level)}
      </div>
      <dl className="tip-grid">
        <dt>MAE</dt>
        <dd>{MW(d.mae_mw)}</dd>
        <dt>Bias</dt>
        <dd>{signedMW(d.bias_mw)}</dd>
        <dt>nMAE</dt>
        <dd>{pct(d.nmae_pct, 2)}</dd>
        <dt>Periods</dt>
        <dd>{d.count.toLocaleString('en-GB')}</dd>
      </dl>
    </div>
  )
}

function hourTakeaway(rows) {
  const scored = rows.filter((r) => r.count > 0 && r.mae_mw != null)
  if (scored.length < 2) return null
  const worst = scored.reduce((a, b) => (b.mae_mw > a.mae_mw ? b : a))
  const best = scored.reduce((a, b) => (b.mae_mw < a.mae_mw ? b : a))
  const swing = ((worst.mae_mw - best.mae_mw) / best.mae_mw) * 100
  const hh = (h) => `${String(h).padStart(2, '0')}:00`
  return `Error peaks at ${hh(worst.hour)} (${MW(worst.mae_mw)}) and is lowest at ${hh(
    best.hour,
  )} (${MW(best.mae_mw)}) — a ${swing.toFixed(0)}% swing across the day. Bias runs ${signedMW(
    worst.bias_mw,
  )} at the worst hour against ${signedMW(best.bias_mw)} at the best, so the forecast leans hardest ${
    worst.hour >= 22 || worst.hour <= 6 ? 'overnight' : 'during the day'
  }.`
}

function levelTakeaway(rows) {
  const scored = rows.filter((r) => r.count > 0 && r.mae_mw != null)
  if (!scored.length) return null
  const biggest = scored.reduce((a, b) => (b.count > a.count ? b : a))
  const worstAbs = scored.reduce((a, b) => (b.mae_mw > a.mae_mw ? b : a))
  const worstRel = scored.reduce((a, b) => (b.nmae_pct > a.nmae_pct ? b : a))
  const empty = rows.filter((r) => r.count === 0)
  const same = worstAbs.wind_level === biggest.wind_level
  return `Absolute error grows with the forecast: the worst bucket is ${windBand(
    worstAbs.wind_level,
  )} at ${MW(worstAbs.mae_mw)}${
    same ? ', which is also where most of the month sits' : ''
  } (${biggest.count.toLocaleString('en-GB')} of the periods). Relative error runs the other way — ${windBand(
    worstRel.wind_level,
  )} is the worst proportionally at ${pct(worstRel.nmae_pct, 1)} of the wind involved${
    worstRel.count < 200 ? `, though on only ${worstRel.count} periods` : ''
  }.${
    empty.length
      ? ` The forecast never went ${empty.map((e) => windBand(e.wind_level)).join(' or ')}, so that bucket is empty.`
      : ''
  }`
}

export default function Analysis({ params }) {
  const hour = useEndpoint(
    ({ signal }) => api.errorByHour(params, { signal }),
    [JSON.stringify(params)],
  )
  const level = useEndpoint(
    ({ signal }) => api.errorByLevel(params, { signal }),
    [JSON.stringify(params)],
  )

  const hourText = useMemo(
    () => (hour.data ? hourTakeaway(hour.data.rows) : null),
    [hour.data],
  )
  const levelText = useMemo(
    () => (level.data ? levelTakeaway(level.data.rows) : null),
    [level.data],
  )

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <span className="panel-title">Error by hour of the delivery day</span>
          <span className="panel-note">Europe/London · MAE in MW</span>
          <Info>
            Grouped by the local hour each settlement period is delivered in. A
            diurnal shape usually means the forecast handles some parts of the
            day better than others.
          </Info>
        </div>
        {hour.loading && !hour.data ? (
          <ChartSkeleton height={230} />
        ) : hour.error ? (
          <ErrorState error={hour.error} onRetry={hour.retry} />
        ) : (
          <>
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={hour.data.rows} margin={{ top: 6, right: 8, left: 2, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 4" vertical={false} />
                <XAxis
                  dataKey="hour"
                  tickFormatter={(h) => String(h).padStart(2, '0')}
                  tickLine={false}
                  stroke="var(--line)"
                  interval={1}
                />
                <YAxis
                  tickFormatter={(v) => `${(v / 1000).toFixed(1)}`}
                  width={32}
                  tickLine={false}
                  stroke="var(--line)"
                />
                <Tooltip content={<Tip unit="hour" />} cursor={{ fill: 'var(--forecast-soft)' }} />
                <Bar dataKey="mae_mw" fill="var(--forecast)" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
            <p className="takeaway">{hourText}</p>
          </>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <span className="panel-title">Error by forecast wind level</span>
          <span className="panel-note">bucketed on the forecast, not the actual</span>
          <Info>
            Bucketing on the forecast is the point: at decision time the forecast
            is all you have, so &quot;how wrong is a 12 GW forecast&quot; is a
            question you can act on.
          </Info>
        </div>
        {level.loading && !level.data ? (
          <ChartSkeleton height={230} />
        ) : level.error ? (
          <ErrorState error={level.error} onRetry={level.retry} />
        ) : (
          <>
            <ResponsiveContainer width="100%" height={230}>
              <BarChart
                data={level.data.rows}
                margin={{ top: 6, right: 8, left: 2, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="2 4" vertical={false} />
                <XAxis
                  dataKey="wind_level"
                  tickFormatter={(s) => windBand(s).replace(' GW and above', '+').replace(' GW', '').replace('under ', '<')}
                  tickLine={false}
                  stroke="var(--line)"
                  fontSize={10}
                />
                <YAxis
                  tickFormatter={(v) => `${(v / 1000).toFixed(1)}`}
                  width={32}
                  tickLine={false}
                  stroke="var(--line)"
                />
                <Tooltip content={<Tip unit="level" />} cursor={{ fill: 'var(--forecast-soft)' }} />
                <Bar dataKey="mae_mw" isAnimationActive={false}>
                  {level.data.rows.map((r) => (
                    <Cell
                      key={r.wind_level}
                      fill={r.count === 0 ? 'var(--line)' : 'var(--forecast)'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <p className="panel-note" style={{ marginLeft: 2 }}>
              Buckets in GW of forecast wind. MAE in MW.
            </p>
            <p className="takeaway">{levelText}</p>
          </>
        )}
      </section>
    </>
  )
}
