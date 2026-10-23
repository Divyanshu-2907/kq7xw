import { useEffect, useMemo, useState } from 'react'
import { ApiError, api } from './api.js'
import { useUrlState } from './lib/useUrlState.js'
import { dayUTC } from './lib/format.js'
import TopBar from './components/TopBar.jsx'
import MetricCards from './components/MetricCards.jsx'
import MainChart from './components/MainChart.jsx'
import HorizonChart from './components/HorizonChart.jsx'
import {
  CardsSkeleton,
  ChartSkeleton,
  EmptyState,
  ErrorState,
  Info,
} from './components/States.jsx'

const DEFAULTS = {
  start: '2026-01-05',
  end: '2026-01-11',
  mode: 'horizon',
  horizon: 24,
  cutoff: '09:20',
  theme: 'dark',
}

// Small hook so each panel can show its own skeleton and its own error rather
// than one failure blanking the page.
function useEndpoint(fn, deps, { enabled = true } = {}) {
  const [state, setState] = useState({ loading: enabled, data: null, error: null })
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    if (!enabled) return
    const ac = new AbortController()
    setState((s) => ({ ...s, loading: true, error: null }))
    fn({ signal: ac.signal })
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((err) => {
        if (err.name === 'AbortError') return
        setState({ loading: false, data: null, error: err })
      })
    return () => ac.abort()
  }, [...deps, nonce, enabled])

  return { ...state, retry: () => setNonce((n) => n + 1) }
}

export default function App() {
  const [state, patch] = useUrlState(DEFAULTS)
  const theme = state.theme === 'light' ? 'light' : 'dark'

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  const meta = useEndpoint(({ signal }) => api.meta({ signal }), [])

  const params = useMemo(() => {
    const p = { start: state.start, end: state.end, mode: state.mode }
    if (state.mode === 'horizon') p.horizon = state.horizon
    else p.cutoff = state.cutoff
    return p
  }, [state.start, state.end, state.mode, state.horizon, state.cutoff])

  const series = useEndpoint(
    ({ signal }) => api.series(params, { signal }),
    [JSON.stringify(params)],
  )
  const horizons = useEndpoint(({ signal }) => api.errorByHorizon({ signal }), [])

  const points = series.data?.points ?? []
  const scored = points.filter((p) => p.forecast_mw !== null)
  const rangeLabel = `${dayUTC(`${state.start}T00:00Z`)} – ${dayUTC(`${state.end}T00:00Z`)}`
  const cutoffLabel =
    state.mode === 'horizon'
      ? `${state.horizon} h before delivery`
      : `${state.cutoff} London, day before delivery`

  return (
    <div className="app">
      <TopBar
        state={state}
        patch={patch}
        meta={meta.data}
        theme={theme}
        onToggleTheme={() => patch({ theme: theme === 'dark' ? 'light' : 'dark' })}
      />

      <main>
        {meta.error && <ErrorState error={meta.error} onRetry={meta.retry} />}

        <div className="banner">
          <span aria-hidden="true">⚠</span>
          <div>
            <strong>Known data caveat.</strong> WINDFOR sits about 1.6 GW above
            FUELHH across this month — a vintage published 14 h <em>after</em>{' '}
            delivery is still ~1,600 MW high, and a single scalar removes 47% of
            MAE. The two datasets appear to cover different wind populations, so
            treat raw bias as a scope difference rather than forecast skill.
          </div>
        </div>

        {series.loading && !series.data ? (
          <CardsSkeleton />
        ) : series.error ? null : (
          <MetricCards metrics={series.data?.metrics} />
        )}

        <section className="panel">
          <div className="panel-head">
            <span className="panel-title">Actual vs live forecast</span>
            <span className="panel-note">
              {rangeLabel} · cutoff {cutoffLabel} · times UTC
            </span>
            <Info>
              The forecast line is whichever vintage was newest at the cutoff for
              each delivery period — never one published later. Drag the handles
              under the chart to zoom.
            </Info>
          </div>
          {series.loading && !series.data ? (
            <ChartSkeleton height={300} />
          ) : series.error ? (
            <ErrorState error={series.error} onRetry={series.retry} />
          ) : scored.length === 0 ? (
            <EmptyState
              title="No forecast was available at this cutoff"
              detail={
                state.mode === 'horizon'
                  ? `Nothing was published ${state.horizon} h or more before these delivery periods. Try a shorter horizon.`
                  : `Nothing was published before the ${state.cutoff} gate for these days. Try a later gate.`
              }
            />
          ) : (
            <MainChart points={points} />
          )}
        </section>

        <div className="two-col">
          <section className="panel">
            <div className="panel-head">
              <span className="panel-title">Value of waiting</span>
              <span className="panel-note">
                MAE by horizon, whole month
              </span>
              <Info>
                Every point is its own independent no-lookahead run over all of
                January, so this is not a time series. Deciding later costs less
                error — watch coverage past 42 h, where fewer periods have any
                forecast at all.
              </Info>
            </div>
            {horizons.loading && !horizons.data ? (
              <ChartSkeleton height={212} />
            ) : horizons.error ? (
              <ErrorState error={horizons.error} onRetry={horizons.retry} />
            ) : (
              <HorizonChart
                rows={horizons.data.rows}
                currentHorizon={state.horizon}
                active={state.mode === 'horizon'}
              />
            )}
          </section>

          <section className="panel">
            <div className="panel-head">
              <span className="panel-title">Selection in force</span>
            </div>
            <dl className="tip-grid" style={{ gridTemplateColumns: 'auto 1fr', rowGap: 6 }}>
              <dt>Mode</dt>
              <dd style={{ textAlign: 'left' }}>
                {state.mode === 'horizon' ? 'Horizon' : 'Day-ahead'}
              </dd>
              <dt>Cutoff</dt>
              <dd style={{ textAlign: 'left' }}>{cutoffLabel}</dd>
              <dt>Periods</dt>
              <dd style={{ textAlign: 'left' }}>
                {points.length ? `${points.length} half-hourly` : '—'}
              </dd>
              <dt>Actuals</dt>
              <dd style={{ textAlign: 'left' }}>
                {meta.data?.actual_resolution === 'PT30M' ? 'half-hourly' : '—'}
              </dd>
              <dt>Forecasts</dt>
              <dd style={{ textAlign: 'left' }}>
                {meta.data?.forecast_resolution === 'PT1H' ? 'hourly' : '—'}
              </dd>
            </dl>
            {meta.data && (
              <p className="panel-note" style={{ marginTop: 10 }}>
                {meta.data.resolution_note}
              </p>
            )}
          </section>
        </div>
      </main>

      <footer>
        Elexon BMRS · FUELHH actuals (fuelType WIND) vs WINDFOR forecasts ·
        January 2026 · all values MW, all timestamps UTC · error = forecast −
        actual
      </footer>
    </div>
  )
}
