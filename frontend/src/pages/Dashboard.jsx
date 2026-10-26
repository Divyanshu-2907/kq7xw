import { api } from '../api.js'
import { useEndpoint } from '../lib/useEndpoint.js'
import { useIsNarrow } from '../lib/useIsNarrow.js'
import { dayUTC } from '../lib/format.js'
import MetricCards from '../components/MetricCards.jsx'
import MainChart from '../components/MainChart.jsx'
import HorizonChart from '../components/HorizonChart.jsx'
import {
  CardsSkeleton,
  ChartSkeleton,
  EmptyState,
  ErrorState,
  Info,
} from '../components/States.jsx'

// Order matters here: the number to act on, then the chart it came from.
// Anything explanatory sits below the fold or behind a control.

export default function Dashboard({ state, params, meta, onPickSlot, onOpenTab }) {
  // A 420px chart leaves only a sliver visible on a phone.
  const chartHeight = useIsNarrow() ? 300 : 420
  const series = useEndpoint(
    ({ signal }) => api.series(params, { signal }),
    [JSON.stringify(params)],
  )
  // The hero card's number: what you could have committed to, and whether that
  // promise held.
  const plan = useEndpoint(
    ({ signal }) => api.plan({ ...params, confidence: 0.9 }, { signal }),
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
  const count = series.data?.metrics?.count

  return (
    <>
      {series.loading && !series.data ? (
        <CardsSkeleton count={4} />
      ) : series.error ? null : (
        <MetricCards
          metrics={series.data?.metrics}
          adjusted={series.data?.adjusted}
          plan={plan.data}
          planLoading={plan.loading}
        />
      )}

      <p className="scope-note">
        Note: WINDFOR runs about 1.16× above metered FUELHH output; the scope
        adjustment removes 46.5% of MAE.{' '}
        <button type="button" className="linkish" onClick={() => onOpenTab('quality')}>
          Details →
        </button>
      </p>

      <section className="panel">
        <div className="panel-head">
          <span className="panel-title">Actual vs live forecast</span>
          <span className="panel-note">
            {rangeLabel} · cutoff {cutoffLabel}
            {count ? ` · ${count.toLocaleString('en-GB')} half-hourly periods` : ''} ·
            times UTC
          </span>
          <Info>
            The forecast line is whichever vintage was newest at the cutoff for
            each delivery period — never one published later. Drag the handles
            under the chart to zoom, and click any point to see every forecast
            ever published for it.
          </Info>
        </div>
        {series.loading && !series.data ? (
          <ChartSkeleton height={chartHeight} />
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
          <MainChart points={points} height={chartHeight} onPickSlot={onPickSlot} />
        )}
      </section>

      <div className="two-col">
        <section className="panel">
          <div className="panel-head">
            <span className="panel-title">Value of waiting</span>
            <span className="panel-note">MAE by horizon, whole month</span>
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
              {meta?.actual_resolution === 'PT30M' ? 'half-hourly' : '—'}
            </dd>
            <dt>Forecasts</dt>
            <dd style={{ textAlign: 'left' }}>
              {meta?.forecast_resolution === 'PT1H' ? 'hourly' : '—'}
            </dd>
          </dl>
          {meta && (
            <p className="panel-note" style={{ marginTop: 10 }}>
              {meta.resolution_note}
            </p>
          )}
        </section>
      </div>
    </>
  )
}
