// Thin fetch layer. Base URL comes from the environment so the same build can
// point at a local backend or at the deployed one.

/** Port the backend listens on during `npm run dev`. */
export const DEV_API_PORT = 8000

/**
 * Resolve the API base URL from a Vite-style env object.
 *
 * An explicit `VITE_API_BASE` always wins, including an empty string, which is
 * how the Docker build asks for same-origin.
 *
 * Otherwise the default depends on where the bundle is running, and getting
 * this wrong is deployable: an unconditional `http://localhost:8000` fallback
 * was once baked into the production bundle, so the deployed app tried to call
 * the viewer's own machine. In production nothing is served on localhost, so
 * the only sane default is same-origin — an empty base, giving relative
 * `/api/...` paths that both nginx and the Vercel rewrite route to the backend.
 *
 * `npm run dev` is the one case where the API genuinely lives on another port,
 * and the address is derived from wherever the page was loaded rather than
 * hard-coded. That keeps every local address out of the production bundle (it
 * is greppable, and a reviewer will grep), and it means opening the dev server
 * from a phone on the same network reaches the backend on that host too, which
 * a literal `localhost` could not.
 *
 * Exported so it can be tested without building or mocking `import.meta`.
 */
export function resolveApiBase(env = {}, loc = globalThis.location) {
  const configured = env.VITE_API_BASE
  if (configured !== undefined && configured !== null) {
    return String(configured).replace(/\/$/, '')
  }
  if (!env.DEV || !loc?.hostname) return ''
  return `${loc.protocol}//${loc.hostname}:${DEV_API_PORT}`
}

const BASE = resolveApiBase(import.meta.env)

export class ApiError extends Error {
  constructor(message, status, url) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.url = url
  }
}

function qs(params) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export async function get(path, params = {}, { signal } = {}) {
  const url = `${BASE}${path}${qs(params)}`
  let res
  try {
    res = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    // Network-level failure: the API is almost always simply not running.
    // With a same-origin base there is no host worth naming, so say where it
    // looked rather than printing an empty string.
    throw new ApiError(
      BASE
        ? `Could not reach the API at ${BASE}. Is the backend running?`
        : `Could not reach the API at ${path}. Is the backend running?`,
      0,
      url,
    )
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        detail = body.detail.map((d) => `${d.loc?.at(-1) ?? ''}: ${d.msg}`).join('; ')
      }
    } catch {
      /* keep the status line */
    }
    throw new ApiError(detail, res.status, url)
  }
  return res.json()
}

export const api = {
  meta: (o) => get('/api/meta', {}, o),
  series: (p, o) => get('/api/series', p, o),
  metrics: (p, o) => get('/api/metrics', p, o),
  errorByHorizon: (o) => get('/api/error-by-horizon', {}, o),
  errorByHour: (p, o) => get('/api/error-by-hour', p, o),
  errorByLevel: (p, o) => get('/api/error-by-level', p, o),
  calibration: (p, o) => get('/api/calibration', p, o),
  plan: (p, o) => get('/api/plan', p, o),
  replay: (p, o) => get('/api/replay', p, o),
  slot: (p, o) => get('/api/slot', p, o),
  misses: (p, o) => get('/api/misses', p, o),
  dataQuality: (o) => get('/api/data-quality', {}, o),
}
