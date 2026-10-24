import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api.js'
import { useEndpoint } from '../lib/useEndpoint.js'
import { MW, dayUTC, stampUTC, timeUTC } from '../lib/format.js'
import { ChartSkeleton, ErrorState, Info } from '../components/States.jsx'

// Decision Replay: the day as it looked from inside the decision, not after it.
// Drag the slider back to any publication and the chart shows only what had
// been published by then. The actual stays hidden until the slider reaches
// delivery, because on the day you did not have it either.

const TRAIL = 5 // how many older vintages fade behind the current one
const STEP_MS = 850

export default function Replay({ day, cutoff }) {
  const replay = useEndpoint(
    ({ signal }) => api.replay({ day, cutoff }, { signal }),
    [day, cutoff],
  )
  const [idx, setIdx] = useState(0)
  const [playing, setPlaying] = useState(false)
  const timer = useRef(null)

  // Memoised so the hooks below can list them as dependencies: a fresh []
  // each render would retrigger the effects forever.
  const vintages = useMemo(() => replay.data?.vintages ?? [], [replay.data])
  const publishTimes = useMemo(() => replay.data?.publish_times ?? [], [replay.data])
  const last = publishTimes.length - 1

  // Open on the last vintage that was actually available at the gate: that is
  // the one the desk traded on.
  useEffect(() => {
    if (!replay.data) return
    const eligible = vintages.filter((v) => v.eligible_at_cutoff).length
    setIdx(eligible > 0 ? eligible - 1 : 0)
    setPlaying(false)
  }, [replay.data, vintages])

  // Arrow keys step through publications without having to focus the slider.
  useEffect(() => {
    const onKey = (e) => {
      const tag = e.target?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        e.preventDefault()
        setPlaying(false)
        setIdx((i) => Math.min(last, Math.max(0, i + (e.key === 'ArrowRight' ? 1 : -1))))
      } else if (e.key === 'Home') {
        e.preventDefault()
        setPlaying(false)
        setIdx(0)
      } else if (e.key === 'End') {
        e.preventDefault()
        setPlaying(false)
        setIdx(last)
      } else if (e.key === ' ') {
        e.preventDefault()
        setPlaying((p) => !p)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [last])

  useEffect(() => {
    if (!playing) return
    timer.current = setInterval(() => {
      setIdx((i) => {
        if (i >= last) {
          setPlaying(false)
          return i
        }
        return i + 1
      })
    }, STEP_MS)
    return () => clearInterval(timer.current)
  }, [playing, last])

  const current = vintages[idx]
  const now = publishTimes[idx] ? new Date(publishTimes[idx]).getTime() : null
  const cutoffMs = replay.data ? new Date(replay.data.cutoff).getTime() : null
  const afterGate = now != null && cutoffMs != null && now > cutoffMs

  // One row per delivery hour, carrying the current vintage plus its trail.
  const data = useMemo(() => {
    if (!replay.data) return []
    const rows = new Map()
    const add = (iso, key, mw) => {
      const t = new Date(iso).getTime()
      if (!rows.has(t)) rows.set(t, { t })
      rows.get(t)[key] = mw
    }
    for (let back = TRAIL; back >= 1; back--) {
      const v = vintages[idx - back]
      if (v) v.points.forEach((p) => add(p.start_time, `trail${back}`, p.forecast_mw))
    }
    if (current) current.points.forEach((p) => add(p.start_time, 'current', p.forecast_mw))
    // The actual is revealed only as far as the slider has travelled.
    for (const a of replay.data.actuals) {
      if (now != null && new Date(a.start_time).getTime() <= now) {
        add(a.start_time, 'actual', a.actual_mw)
      } else {
        add(a.start_time, 'actual', null)
      }
    }
    return [...rows.values()].sort((a, b) => a.t - b.t)
  }, [replay.data, idx, now, current, vintages])

  // Narrative hour: the period the DESK got most wrong, judged by the vintage
  // that was live at the gate. Judging it by a vintage published after delivery
  // would pick the hour hindsight disagrees with, which is a different question.
  const focus = useMemo(() => {
    if (!replay.data) return null
    const live =
      vintages.find((v) => v.is_live) ??
      [...vintages].reverse().find((v) => v.eligible_at_cutoff) ??
      vintages.at(-1)
    if (!live) return null
    let best = null
    for (const a of replay.data.actuals) {
      const f = live.points.find((p) => p.start_time === a.start_time)
      if (!f) continue
      const err = Math.abs(f.forecast_mw - a.actual_mw)
      if (!best || err > best.err) best = { iso: a.start_time, err, actual: a.actual_mw }
    }
    return best
  }, [replay.data, vintages])

  const focusForecast = focus && current
    ? current.points.find((p) => p.start_time === focus.iso)?.forecast_mw
    : null
  const focusRevealed =
    focus && now != null && new Date(focus.iso).getTime() <= now

  if (replay.loading && !replay.data) return <ChartSkeleton height={360} />
  if (replay.error) return <ErrorState error={replay.error} onRetry={replay.retry} />
  if (!publishTimes.length) {
    return (
      <section className="panel">
        <div className="state">
          <div className="state-title">No forecasts were published for {day}</div>
        </div>
      </section>
    )
  }

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <span className="panel-title">Decision Replay</span>
          <span className="panel-note">
            {dayUTC(`${day}T00:00Z`)} delivery · what was on screen at each
            publication · ← → to step, space to play
          </span>
          <Info>
            Drag or play to move through every forecast published for this day.
            Older vintages fade behind the current one. The actual only draws in
            as the slider passes each delivery period, because that is when you
            would have known it.
          </Info>
        </div>

        <div className="replay-controls">
          <button
            type="button"
            className="ghost-btn play"
            onClick={() => (idx >= last ? (setIdx(0), setPlaying(true)) : setPlaying((p) => !p))}
            aria-label={playing ? 'Pause' : 'Play'}
          >
            {playing ? '❚❚ Pause' : idx >= last ? '↻ Replay' : '▶ Play'}
          </button>

          <div className="slider-stack">
            <input
              type="range"
              min={0}
              max={last}
              value={idx}
              aria-valuetext={`Published ${stampUTC(publishTimes[idx])}`}
              onChange={(e) => {
                setPlaying(false)
                setIdx(Number(e.target.value))
              }}
              aria-label="Publication time"
              className="replay-range"
            />
            {/* The gate falls on the day BEFORE delivery, so it cannot sit on the
                chart's delivery-time axis. It belongs on this publish timeline. */}
            <div className="timeline">
              {publishTimes.map((p, i) => {
                const eligible = new Date(p).getTime() <= cutoffMs
                return (
                  <span
                    key={p}
                    className={`tick${i === idx ? ' at' : ''}${eligible ? '' : ' late'}`}
                    style={{ left: `${(i / Math.max(last, 1)) * 100}%` }}
                  />
                )
              })}
              <span
                className="gate"
                style={{
                  left: `${(vintages.filter((v) => v.eligible_at_cutoff).length - 0.5) / Math.max(last, 1) * 100}%`,
                }}
              >
                <span className="gate-label">auction closes {replay.data.cutoff_local_time}</span>
              </span>
            </div>
          </div>

          <div className={`vintage-stamp${afterGate ? ' late' : ''}`}>
            <span className="vintage-time">{stampUTC(publishTimes[idx])}</span>
            <span className="vintage-tag">
              {afterGate
                ? 'published after the gate — not available to the buy'
                : current?.is_live
                  ? 'the vintage the gate locked in'
                  : `${idx + 1} of ${publishTimes.length} · still before the gate`}
            </span>
          </div>
        </div>

        <ResponsiveContainer width="100%" height={330}>
          <ComposedChart data={data} margin={{ top: 20, right: 10, left: 2, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={['dataMin', 'dataMax']}
              tickFormatter={(t) => timeUTC(new Date(t).toISOString())}
              minTickGap={34}
              tickLine={false}
              stroke="var(--line)"
            />
            <YAxis
              tickFormatter={(v) => `${(v / 1000).toFixed(1)}`}
              width={36}
              tickLine={false}
              stroke="var(--line)"
              /* Vintages for one day differ by a few hundred MW. A zero-based
                 axis would flatten them into one line and hide the point. */
              domain={['dataMin - 800', 'dataMax + 800']}
            />
            {now != null && data.length > 0 && now >= data[0].t && now <= data.at(-1).t && (
              <ReferenceLine
                x={now}
                stroke="var(--warn)"
                strokeDasharray="3 3"
                label={{
                  value: 'published',
                  position: 'top',
                  fill: 'var(--warn)',
                  fontSize: 10,
                }}
              />
            )}
            {[5, 4, 3, 2, 1].map((back) => (
              <Line
                key={back}
                dataKey={`trail${back}`}
                stroke="var(--forecast)"
                strokeOpacity={0.1 + (TRAIL - back) * 0.09}
                strokeWidth={1}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            ))}
            <Line
              dataKey="current"
              stroke="var(--forecast)"
              strokeWidth={2}
              strokeDasharray="5 3"
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              dataKey="actual"
              stroke="var(--actual)"
              strokeWidth={1.6}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
          </ComposedChart>
        </ResponsiveContainer>

        <div className="legend" style={{ marginTop: 4 }}>
          <span>
            <i className="swatch dashed" style={{ background: 'var(--forecast)' }} /> This
            vintage (dashed)
          </span>
          <span>
            <i className="swatch" style={{ background: 'var(--forecast)', opacity: 0.35 }} />{' '}
            Up to {TRAIL} earlier vintages
          </span>
          <span>
            <i className="swatch" style={{ background: 'var(--actual)' }} /> Actual, as it
            became known
          </span>
          <span style={{ color: 'var(--text-faint)' }}>
            axis GW, zoomed to the day · values MW
          </span>
        </div>
      </section>

      {focus && (
        <section className="panel narrative">
          <p>
            At <strong>{stampUTC(publishTimes[idx])}</strong>, the forecast for{' '}
            <strong>{timeUTC(focus.iso)}</strong>{' '}
            {focusForecast == null ? (
              <span style={{ color: 'var(--text-faint)' }}>
                had not been published yet — this vintage does not reach that far.
              </span>
            ) : (
              <>
                was <strong>{MW(focusForecast)}</strong>.{' '}
              </>
            )}
            {focusForecast != null && focusRevealed ? (
              <>
                It turned out to be <strong>{MW(focus.actual)}</strong> — a miss of{' '}
                <strong>{MW(Math.abs(focusForecast - focus.actual))}</strong>.
              </>
            ) : focusForecast != null ? (
              <span style={{ color: 'var(--text-faint)' }}>
                That period has not been delivered yet at this point in the replay.
              </span>
            ) : null}
          </p>
          <p className="panel-note">
            Showing the period this day missed by most, judged by the vintage
            that was live at the gate. Everything above is drawn only from
            publications at or before the slider.
          </p>
        </section>
      )}
    </>
  )
}
