import { useEffect, useMemo, useState } from 'react'
import { api } from './api.js'
import { useEndpoint } from './lib/useEndpoint.js'
import { useUrlState } from './lib/useUrlState.js'
import TopBar from './components/TopBar.jsx'
import SlotDrawer from './components/SlotDrawer.jsx'
import HowToRead, { hasSeenHowTo, markHowToSeen } from './components/HowToRead.jsx'
import { ErrorState } from './components/States.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Replay from './pages/Replay.jsx'
import Plan from './pages/Plan.jsx'
import Misses from './pages/Misses.jsx'
import Analysis from './pages/Analysis.jsx'
import Quality from './pages/Quality.jsx'

const DEFAULTS = {
  tab: 'dashboard',
  start: '2026-01-05',
  end: '2026-01-11',
  mode: 'horizon',
  horizon: 24,
  cutoff: '09:20',
  theme: 'dark',
  day: '',
  confidence: 0.9,
  cost_ratio: 3,
  slot: '',
}

const TABS = [
  ['dashboard', 'Dashboard'],
  ['replay', 'Decision Replay'],
  ['plan', 'Plan'],
  ['misses', 'Biggest misses'],
  ['analysis', 'Analysis'],
  ['quality', 'Data quality'],
]

// Tabs that read a date range and cutoff from the top bar. Replay drives its
// own day, and Data quality describes the whole snapshot either way.
const RANGE_TABS = new Set(['dashboard', 'plan', 'misses', 'analysis'])

export default function App() {
  const [state, patch] = useUrlState(DEFAULTS)
  const theme = state.theme === 'light' ? 'light' : 'dark'

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  const meta = useEndpoint(({ signal }) => api.meta({ signal }), [])

  const [howToOpen, setHowToOpen] = useState(false)
  useEffect(() => {
    if (!hasSeenHowTo()) setHowToOpen(true)
  }, [])
  const closeHowTo = () => {
    setHowToOpen(false)
    markHowToSeen()
  }

  const params = useMemo(() => {
    const p = { start: state.start, end: state.end, mode: state.mode }
    if (state.mode === 'horizon') p.horizon = state.horizon
    else p.cutoff = state.cutoff
    return p
  }, [state.start, state.end, state.mode, state.horizon, state.cutoff])

  // Replay opens on the day of the worst miss unless the URL names one.
  const worst = useEndpoint(
    ({ signal }) =>
      api.misses({ n: 1, mode: 'day_ahead', cutoff: state.cutoff }, { signal }),
    [state.cutoff],
    { enabled: state.tab === 'replay' && !state.day },
  )
  const worstDay = worst.data?.rows?.[0]?.start_time?.slice(0, 10)
  const replayDay = state.day || worstDay

  // Pin the resolved default into the URL, so the date control shows it and the
  // link can be shared as-is.
  useEffect(() => {
    if (state.tab === 'replay' && !state.day && worstDay) patch({ day: worstDay })
  }, [state.tab, state.day, worstDay, patch])

  const openDay = (day) => patch({ tab: 'replay', day })

  return (
    <div className="app">
      <TopBar
        state={state}
        patch={patch}
        meta={meta.data}
        theme={theme}
        onToggleTheme={() => patch({ theme: theme === 'dark' ? 'light' : 'dark' })}
        showRangeControls={RANGE_TABS.has(state.tab)}
        howToOpen={howToOpen}
        onToggleHowTo={() => (howToOpen ? closeHowTo() : setHowToOpen(true))}
        howTo={howToOpen ? <HowToRead onClose={closeHowTo} /> : null}
      />

      <nav className="tabs" aria-label="Views">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            className="tab"
            aria-current={state.tab === id ? 'page' : undefined}
            onClick={() => patch({ tab: id })}
          >
            {label}
          </button>
        ))}
      </nav>

      <main>
        {meta.error && <ErrorState error={meta.error} onRetry={meta.retry} />}

        {state.tab === 'dashboard' && (
          <Dashboard
            state={state}
            params={params}
            meta={meta.data}
            onPickSlot={(iso) => patch({ slot: iso })}
            onOpenTab={(tab) => patch({ tab })}
          />
        )}

        {state.tab === 'replay' &&
          (replayDay ? (
            <Replay day={replayDay} cutoff={state.cutoff} />
          ) : (
            <section className="panel">
              <div className="state">
                <div className="state-title">Finding the day with the biggest miss…</div>
              </div>
            </section>
          ))}

        {state.tab === 'plan' && (
          <Plan
            params={params}
            confidence={Number(state.confidence)}
            costRatio={Number(state.cost_ratio)}
            patch={patch}
          />
        )}

        {state.tab === 'misses' && <Misses params={params} onOpenDay={openDay} />}

        {state.tab === 'analysis' && <Analysis params={params} />}

        {state.tab === 'quality' && <Quality />}
      </main>

      <SlotDrawer
        time={state.slot}
        params={params}
        onClose={() => patch({ slot: '' })}
      />

      <footer>
        Elexon BMRS · FUELHH actuals (fuelType WIND) vs WINDFOR forecasts ·
        January 2026 · all values MW, all timestamps UTC · error = forecast −
        actual
      </footer>
    </div>
  )
}
