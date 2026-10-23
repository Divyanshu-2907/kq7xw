import { useCallback, useEffect, useState } from 'react'

// Every control lives in the query string, so any view can be pasted into a
// chat and opened exactly as the sender saw it. The URL is the single source of
// truth; React state is just a mirror of it.

function read(defaults) {
  const sp = new URLSearchParams(window.location.search)
  const out = { ...defaults }
  for (const key of Object.keys(defaults)) {
    const raw = sp.get(key)
    if (raw === null) continue
    out[key] = typeof defaults[key] === 'number' ? Number(raw) : raw
  }
  return out
}

function write(state, defaults) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(state)) {
    // Leave defaults out so a shared link carries only what was changed.
    if (v === undefined || v === null || v === '' || v === defaults[k]) continue
    sp.set(k, String(v))
  }
  const q = sp.toString()
  const url = `${window.location.pathname}${q ? `?${q}` : ''}`
  window.history.replaceState(null, '', url)
}

export function useUrlState(defaults) {
  const [state, setState] = useState(() => read(defaults))

  // Back/forward should move the controls, not just the address bar.
  useEffect(() => {
    const onPop = () => setState(read(defaults))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  useEffect(() => {
    write(state, defaults)
  }, [state])

  const patch = useCallback((changes) => {
    setState((prev) => ({ ...prev, ...changes }))
  }, [])

  return [state, patch]
}
