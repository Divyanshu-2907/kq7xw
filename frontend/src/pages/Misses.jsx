import { api } from '../api.js'
import { useEndpoint } from '../lib/useEndpoint.js'
import { MW, dayUTC, hours, signedMW, timeUTC } from '../lib/format.js'
import { ErrorState, Info, Skeleton } from '../components/States.jsx'

// The ten periods this forecast got most wrong, and whether each was a matter
// of timing or of level.

export default function Misses({ params, onOpenDay }) {
  const misses = useEndpoint(
    ({ signal }) => api.misses({ ...params, n: 10 }, { signal }),
    [JSON.stringify(params)],
  )

  if (misses.loading && !misses.data) {
    return (
      <section className="panel">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} height={26} style={{ marginBottom: 6 }} />
        ))}
      </section>
    )
  }
  if (misses.error) return <ErrorState error={misses.error} onRetry={misses.retry} />

  const rows = misses.data.rows
  const days = new Set(rows.map((r) => r.start_time.slice(0, 10)))

  return (
    <section className="panel">
      <div className="panel-head">
        <span className="panel-title">Biggest misses</span>
        <span className="panel-note">
          worst {rows.length} periods by absolute error · click any row to replay that day
        </span>
        <Info>
          Timing vs size: the forecast curve is shifted by −3 to +3 hours and
          scored on the same periods each time. If the best shift removes at
          least half the local error, the forecast had the right shape at the
          wrong time; otherwise it had the level wrong.
        </Info>
      </div>

      {days.size <= 2 && (
        <div className="badge warn" style={{ marginBottom: 10 }}>
          <strong>Heads up.</strong> All {rows.length} of these fall on{' '}
          {days.size === 1 ? 'a single day' : 'two days'} (
          {[...days].map((d) => dayUTC(`${d}T00:00Z`)).join(', ')}). One bad day
          produces many consecutive bad half-hours, so this is really a list of
          days, not of independent events.
        </div>
      )}

      <div className="table-scroll">
        <table className="misses">
          <thead>
            <tr>
              <th>#</th>
              <th>Delivery</th>
              <th className="r">Forecast</th>
              <th className="r">Actual</th>
              <th className="r">Error</th>
              <th className="r">Lead</th>
              <th>Type</th>
              <th className="r">Best shift</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.start_time}
                onClick={() => onOpenDay(r.start_time.slice(0, 10))}
                tabIndex={0}
                role="button"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onOpenDay(r.start_time.slice(0, 10))
                  }
                }}
              >
                <td className="dim">{r.rank}</td>
                <td>
                  {dayUTC(r.start_time)}{' '}
                  <span className="dim">{timeUTC(r.start_time)}</span>
                </td>
                <td className="r num">{MW(r.forecast_mw)}</td>
                <td className="r num">{MW(r.actual_mw)}</td>
                <td className={`r num ${r.error_mw > 0 ? 'over' : 'under'}`}>
                  {signedMW(r.error_mw)}
                </td>
                <td className="r num dim">{hours(r.lead_h)}</td>
                <td>
                  <span className={`tag ${r.miss_type}`}>{r.miss_type}</span>
                </td>
                <td className="r num dim">
                  {r.best_shift_h == null
                    ? '—'
                    : r.best_shift_h === 0
                      ? 'none helps'
                      : `${r.best_shift_h > 0 ? '+' : ''}${r.best_shift_h} h`}
                  {r.error_removed_by_shift_pct != null && r.best_shift_h !== 0 && (
                    <span className="dim">
                      {' '}
                      ({r.error_removed_by_shift_pct.toFixed(0)}%)
                    </span>
                  )}
                </td>
                <td className="dim">replay →</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
