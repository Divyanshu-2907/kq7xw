import { Info } from './States.jsx'

// The whole decision context in one strip: which days, which cutoff rule, and
// how far ahead of delivery the call is being made.

export default function TopBar({ state, patch, meta, theme, onToggleTheme, showRangeControls = true }) {
  const minDate = meta ? meta.target_start.slice(0, 10) : '2026-01-01'
  const maxDate = meta
    ? new Date(new Date(meta.target_end).getTime() - 86400000).toISOString().slice(0, 10)
    : '2026-01-31'
  const maxH = meta?.horizon?.max_h ?? 42
  const dayAhead = state.mode === 'day_ahead'

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-name">Headroom</span>
        <span className="brand-sub">
          Wind you can count on before the day-ahead gate
        </span>
      </div>

      {state.tab === 'replay' && (
        <div className="control">
          <span className="control-label">Delivery day</span>
          <input
            type="date"
            value={state.day || ''}
            min={minDate}
            max={maxDate}
            onChange={(e) => patch({ day: e.target.value })}
            aria-label="Delivery day to replay"
          />
        </div>
      )}

      {showRangeControls && (
      <div className="control control-dates">
        <span className="control-label">Delivery dates</span>
        <div className="control-row">
          <input
            type="date"
            value={state.start}
            min={minDate}
            max={state.end || maxDate}
            onChange={(e) => patch({ start: e.target.value })}
            aria-label="First delivery date"
          />
          <span style={{ color: 'var(--text-faint)' }}>to</span>
          <input
            type="date"
            value={state.end}
            min={state.start || minDate}
            max={maxDate}
            onChange={(e) => patch({ end: e.target.value })}
            aria-label="Last delivery date"
          />
        </div>
      </div>
      )}

      {state.tab !== 'replay' && (
      <div className="control">
        <span className="control-label">
          Cutoff rule{' '}
          <Info>
            The live forecast is the newest one published at or before the cutoff.
            Anything published later was not available when the buy was made.
          </Info>
        </span>
        <div className="toggle" role="group" aria-label="Cutoff mode">
          <button
            type="button"
            aria-pressed={!dayAhead}
            onClick={() => patch({ mode: 'horizon' })}
          >
            Horizon
          </button>
          <button
            type="button"
            aria-pressed={dayAhead}
            onClick={() => patch({ mode: 'day_ahead' })}
          >
            Day-ahead
          </button>
        </div>
      </div>
      )}

      {dayAhead || state.tab === 'replay' ? (
        <div className="control">
          <span className="control-label">
            Gate (London){' '}
            <Info>
              {meta?.day_ahead_cutoff_note ??
                'Clock time on the day before delivery, Europe/London.'}
            </Info>
          </span>
          <input
            type="time"
            value={state.cutoff}
            onChange={(e) => patch({ cutoff: e.target.value })}
            aria-label="Day-ahead gate closure time, Europe/London"
          />
        </div>
      ) : (
        <div className="control control-horizon">
          <span className="control-label">
            Horizon{' '}
            <Info>
              Hours before delivery that the decision is made. Cutoff = delivery
              time minus this. Data supports up to {maxH} h at full coverage.
            </Info>
          </span>
          <div className="control-row">
            <input
              type="range"
              min={0}
              max={maxH}
              step={1}
              value={state.horizon}
              onChange={(e) => patch({ horizon: Number(e.target.value) })}
              aria-label="Horizon in hours before delivery"
            />
            <span className="horizon-readout">{state.horizon} h</span>
          </div>
        </div>
      )}

      <div className="spacer" />

      <button
        className="ghost-btn"
        type="button"
        onClick={onToggleTheme}
        aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      >
        {theme === 'dark' ? 'Light' : 'Dark'}
      </button>
    </header>
  )
}
