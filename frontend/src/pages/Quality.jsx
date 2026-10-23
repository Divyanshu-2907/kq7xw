import { api } from '../api.js'
import { useEndpoint } from '../lib/useEndpoint.js'
import { MW, pct, stampUTC } from '../lib/format.js'
import { ErrorState, Info, Skeleton } from '../components/States.jsx'

// What the snapshot actually contains, checked live rather than asserted.

export default function Quality() {
  const dq = useEndpoint(({ signal }) => api.dataQuality({ signal }), [])

  if (dq.loading && !dq.data) {
    return (
      <section className="panel">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} height={22} style={{ marginBottom: 7 }} />
        ))}
      </section>
    )
  }
  if (dq.error) return <ErrorState error={dq.error} onRetry={dq.retry} />
  const d = dq.data

  const clean =
    d.actual_periods_missing.length === 0 &&
    d.actual_duplicate_start_times === 0 &&
    d.forecast_duplicate_keys === 0

  const checks = [
    ['Actual periods', `${d.actual_rows.toLocaleString('en-GB')} of ${d.actual_periods_expected.toLocaleString('en-GB')} expected`, d.actual_rows === d.actual_periods_expected],
    ['Coverage', pct(d.actual_coverage_pct), d.actual_coverage_pct === 100],
    ['Missing intervals', d.actual_periods_missing.length === 0 ? 'none' : `${d.actual_periods_missing.length}`, d.actual_periods_missing.length === 0],
    ['Duplicate actuals', `${d.actual_duplicate_start_times}`, d.actual_duplicate_start_times === 0],
    ['Forecast rows', d.forecast_rows.toLocaleString('en-GB'), true],
    ['Duplicate forecast keys', `${d.forecast_duplicate_keys}`, d.forecast_duplicate_keys === 0],
    ['Publications', `${d.distinct_publish_times} distinct publish times`, true],
    ['Lead time range', `${d.forecast_lead_h_min} h to ${d.forecast_lead_h_max} h`, true],
    ['Backcast rows (negative lead)', d.forecast_negative_lead_rows.toLocaleString('en-GB'), true],
    ['Actual range', `${MW(d.actual_mw_min)} to ${MW(d.actual_mw_max)}`, true],
    ['Zero or negative actuals', `${d.actual_zero_or_negative_periods}`, d.actual_zero_or_negative_periods === 0],
  ]

  const odd = Object.entries(d.publish_clock_times).filter(([, n]) => n < 30)

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <span className="panel-title">Data quality</span>
          <span className="panel-note">live checks over the committed snapshot</span>
          <Info>
            These are recomputed from the snapshot on every request rather than
            copied from the ingest log, so a discrepancy between the two shows up
            here instead of staying hidden.
          </Info>
        </div>

        <div className={`badge ${clean ? 'ok' : 'warn'}`}>
          <strong>{clean ? 'Snapshot is complete.' : 'Snapshot has gaps.'}</strong>{' '}
          {clean
            ? 'Every expected settlement period is present, with no duplicates in either dataset and nothing interpolated.'
            : 'See the table below. Nothing is interpolated, so a gap shrinks the sample rather than being filled with a guess.'}
        </div>

        <div className="table-scroll">
          <table className="misses">
            <tbody>
              {checks.map(([k, v, ok]) => (
                <tr key={k}>
                  <td style={{ width: '48%' }}>{k}</td>
                  <td className="num">{v}</td>
                  <td style={{ width: 62 }}>
                    <span className={`tag ${ok ? 'size' : 'timing'}`}>
                      {ok ? 'ok' : 'check'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <span className="panel-title">Publication schedule</span>
          <span className="panel-note">days on which each clock time appeared</span>
        </div>
        <div className="chips">
          {Object.entries(d.publish_clock_times).map(([t, n]) => (
            <span className={`chip${n < 30 ? ' odd' : ''}`} key={t}>
              {t} <span className="dim">×{n}</span>
            </span>
          ))}
        </div>
        {odd.length > 0 && (
          <p className="panel-note" style={{ marginTop: 8 }}>
            {odd
              .map(([t, n]) => `${t} appears on only ${n} day${n === 1 ? '' : 's'}`)
              .join('; ')}
            . The regular schedule is eight publications a day, so anything else
            is a one-off that replaced a scheduled slot.
          </p>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <span className="panel-title">How each issue is handled</span>
        </div>
        <dl className="handling">
          {Object.entries(d.handling).map(([k, v]) => (
            <div key={k}>
              <dt>{k.replace(/_/g, ' ')}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="panel">
        <div className="panel-head">
          <span className="panel-title">Coverage per day</span>
          <span className="panel-note">settlement periods present, of 48</span>
        </div>
        <div className="daybars">
          {d.coverage_per_day.map((day) => (
            <div
              className="daybar"
              key={day.date}
              title={`${day.date}: ${day.periods} of 48 periods, mean ${Math.round(day.mean_mw)} MW`}
            >
              <span className="fill" style={{ height: `${day.coverage_pct}%` }} />
              <span className="daylabel">{day.date.slice(8)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <span className="panel-title">Provenance</span>
        </div>
        <dl className="tip-grid" style={{ gridTemplateColumns: 'auto 1fr', rowGap: 5 }}>
          <dt>Fetched</dt>
          <dd style={{ textAlign: 'left' }}>{stampUTC(d.ingest.generated_at_utc)}</dd>
          <dt>Actuals</dt>
          <dd style={{ textAlign: 'left' }}>{d.ingest.source?.actuals}</dd>
          <dt>Forecasts</dt>
          <dd style={{ textAlign: 'left' }}>{d.ingest.source?.forecasts}</dd>
          <dt>Source</dt>
          <dd style={{ textAlign: 'left' }}>{d.ingest.source?.base_url}</dd>
        </dl>
      </section>
    </>
  )
}
