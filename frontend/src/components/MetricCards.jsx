import { Info } from './States.jsx'
import { GW, MW, pct, signedMW } from '../lib/format.js'

// The first thing a trader sees. The hero card is the number they can act on;
// the rest explain how much to trust it. Each card carries its unit, and the
// two that the dataset scope offset distorts also show the adjusted figure.

function ScopeLine({ children }) {
  return <div className="metric-adjust">{children}</div>
}

export default function MetricCards({ metrics, adjusted, plan, planLoading }) {
  const m = metrics ?? {}
  // The first week's bands borrow from the whole sample, so its periods are not
  // leakage-free. Lead with the walk-forward reading and keep the other for
  // the tooltip, rather than quietly showing the flattering one.
  const all = plan?.totals
  const t = plan?.walk_forward ?? all
  const shortfall = t?.shortfall_rate_pct
  const warmupExcluded = Boolean(plan?.walk_forward) && all
    ? all.periods - plan.walk_forward.periods
    : 0

  return (
    <div className="cards">
      <div className="card hero">
        <div className="card-label">
          Plan on{' '}
          <Info>
            The megawatts you could have committed to at 90% confidence: the
            forecast minus the error it has historically made at this notice
            period.
            {t?.periods != null && (
              <>
                {' '}Measured over {t.periods.toLocaleString('en-GB')} periods
                whose bands were built only from earlier weeks.
                {warmupExcluded > 0 && (
                  <>
                    {' '}The first {warmupExcluded.toLocaleString('en-GB')}{' '}
                    periods are excluded: with no earlier data to learn from,
                    their bands borrow from the whole month, which would flatter
                    the result
                    {all?.shortfall_rate_pct != null && (
                      <> — including them gives {pct(all.shortfall_rate_pct)}</>
                    )}
                    .
                  </>
                )}
              </>
            )}
          </Info>
        </div>
        <div className="metric-value num hero-value">
          {planLoading && !t ? '—' : GW(t?.mean_plan_mw, 2)}
        </div>
        <div className="metric-plain">
          {shortfall == null ? (
            'at 90% confidence'
          ) : (
            <>
              wind fell below this in{' '}
              <strong className={Math.abs(shortfall - 10) <= 3 ? 'on-target' : 'off-target'}>
                {pct(shortfall)}
              </strong>{' '}
              of periods (target 10%)
            </>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-label">
          MAE{' '}
          <Info>
            Mean absolute error: the average size of the gap between forecast and
            actual. Direction-blind, so over- and under-forecasts do not cancel.
          </Info>
        </div>
        <div className="metric-value num">{MW(m.mae_mw)}</div>
        <div className="metric-plain">Typical miss, ignoring direction</div>
        {adjusted?.mae_mw != null && (
          <ScopeLine>
            {MW(adjusted.mae_mw)} after scope adjustment
          </ScopeLine>
        )}
      </div>

      <div className="card">
        <div className="card-label">
          Level offset{' '}
          <Info>
            Average signed difference (forecast minus actual). Most of it is the
            scope difference between the two datasets rather than forecast
            quality: the adjusted figure below is what remains once the level
            difference is divided out.
          </Info>
        </div>
        <div className="metric-value num">{signedMW(m.bias_mw)}</div>
        <div className="metric-plain">
          Forecast series sits {m.bias_mw >= 0 ? 'above' : 'below'} metered output
        </div>
        {adjusted?.bias_mw != null && (
          <ScopeLine>
            {signedMW(adjusted.bias_mw)} after scope adjustment
          </ScopeLine>
        )}
      </div>

      <div className="card">
        <div className="card-label">
          nMAE{' '}
          <Info>
            MAE as a share of mean actual generation. Used instead of MAPE: wind
            output nears zero often enough that a per-period percentage error
            explodes — a 200 MW miss on a 50 MW hour reads as 400% — and would
            swamp the average.
          </Info>
        </div>
        <div className="metric-value num">{pct(m.nmae_pct)}</div>
        <div className="metric-plain">
          of {MW(m.mean_actual_mw)} mean wind
        </div>
        {adjusted?.nmae_pct != null && (
          <ScopeLine>{pct(adjusted.nmae_pct)} after scope adjustment</ScopeLine>
        )}
      </div>
    </div>
  )
}
