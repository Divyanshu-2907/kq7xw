import { useEffect, useState } from 'react'

// One hook per panel, so a single failing endpoint shows its own error instead
// of blanking the page. Requests abort when their inputs change.
export function useEndpoint(fn, deps, { enabled = true } = {}) {
  const [state, setState] = useState({ loading: enabled, data: null, error: null })
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    if (!enabled) {
      setState({ loading: false, data: null, error: null })
      return
    }
    const ac = new AbortController()
    // Also covers enabled flipping false -> true, where the initial state was
    // built with loading: false.
    setState((s) => ({ ...s, loading: true, error: null }))
    fn({ signal: ac.signal })
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((err) => {
        if (err.name === 'AbortError') return
        setState({ loading: false, data: null, error: err })
      })
    return () => ac.abort()
    // `fn` is an inline closure recreated every render, so the caller's `deps`
    // are the real inputs; spreading them is deliberate.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, enabled])

  return { ...state, retry: () => setNonce((n) => n + 1) }
}
