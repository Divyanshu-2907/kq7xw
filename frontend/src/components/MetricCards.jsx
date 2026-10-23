import { Info } from './States.jsx'
import { MW, biasPhrase, pct } from '../lib/format.js'

// Four numbers a desk actually argues about. Each one carries its unit and a
// plain-English line, because "bias +1,852 MW" means nothing on its own.

export default function MetricCards({ metrics }) {
  const m = metrics ?? {}
  const cards = [
    {
      label: 'MAE',
      value: MW(m.mae_mw),
      plain: 'Typical miss, ignoring direction',
      tip: 'Mean absolute error: average size of the gap between forecast and actual, in MW. Direction-blind, so over- and under-forecasts do not cancel.',
    },
    {
      label: 'RMSE',
      value: MW(m.rmse_mw),
      plain: 'Weights the big misses harder',
      tip: 'Root mean squared error. Squaring before averaging makes one 6 GW day count for far more than six 1 GW days, so it is the number to watch if a single bad period hurts you more than steady small errors.',
    },
    {
      label: 'Bias',
      value: MW(m.bias_mw === null || m.bias_mw === undefined ? null : Math.abs(m.bias_mw)),
      plain: biasPhrase(m.bias_mw),
      tip: 'Average signed error (forecast minus actual). Positive means the forecast runs high, so wind arrives short of what was promised and you end up buying the difference.',
    },
    {
      label: 'nMAE',
      value: pct(m.nmae_pct),
      plain: `MAE as a share of ${MW(m.mean_actual_mw)} mean wind`,
      tip: 'MAE divided by mean actual generation. We use this instead of MAPE: wind output nears zero often enough that a per-period percentage error explodes (a 200 MW miss on a 50 MW hour reads as 400%) and would swamp the average.',
    },
  ]

  return (
    <div className="cards">
      {cards.map((c) => (
        <div className="card" key={c.label}>
          <div className="card-label">
            {c.label} <Info>{c.tip}</Info>
          </div>
          <div className="metric-value num">{c.value}</div>
          <div className="metric-plain">{c.plain}</div>
        </div>
      ))}
      <div className="card">
        <div className="card-label">
          Periods{' '}
          <Info>
            Half-hourly delivery periods in the selection that had both a live
            forecast and a settled actual. Coverage below 100% means some periods
            had no forecast published before the cutoff.
          </Info>
        </div>
        <div className="metric-value num">
          {(m.count ?? 0).toLocaleString('en-GB')}
          <span className="metric-unit">scored</span>
        </div>
        <div className="metric-plain">
          {m.coverage_pct === 100
            ? 'Every period had a forecast in time'
            : `${pct(m.coverage_pct, 1)} coverage — some periods had none`}
        </div>
      </div>
    </div>
  )
}
