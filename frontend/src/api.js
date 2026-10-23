// Thin fetch layer. Base URL comes from the environment so the same build can
// point at a local backend or at the deployed one.
const BASE = (import.meta.env.VITE_API_BASE ?? 'http://localhost:8000').replace(/\/$/, '')

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
    throw new ApiError(
      `Could not reach the API at ${BASE}. Is the backend running?`,
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

export const API_BASE = BASE
