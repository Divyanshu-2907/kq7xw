// One place for units and wording, so no number reaches the screen bare.

export const MW = (v, digits = 0) =>
  v === null || v === undefined || Number.isNaN(v)
    ? '—'
    : `${v.toLocaleString('en-GB', { minimumFractionDigits: digits, maximumFractionDigits: digits })} MW`

export const pct = (v, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : `${v.toFixed(digits)}%`

export const hours = (v, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : `${v.toFixed(digits)} h`

const DT = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  timeZone: 'UTC', hour12: false,
})
const TIME = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit', minute: '2-digit', timeZone: 'UTC', hour12: false,
})
const DAY = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit', month: 'short', timeZone: 'UTC',
})

export const stampUTC = (iso) => (iso ? `${DT.format(new Date(iso))} UTC` : '—')
export const timeUTC = (iso) => (iso ? TIME.format(new Date(iso)) : '—')
export const dayUTC = (iso) => (iso ? DAY.format(new Date(iso)) : '—')

// Bias is the number traders misread most often, so it gets words, not a sign.
export function biasPhrase(bias) {
  if (bias === null || bias === undefined || Number.isNaN(bias)) return 'No bias to report.'
  const mw = MW(Math.abs(bias))
  if (Math.abs(bias) < 1) return 'No systematic lean either way.'
  return bias > 0
    ? `Over-forecasts by ${mw} on average`
    : `Under-forecasts by ${mw} on average`
}

export const signedMW = (v, digits = 0) =>
  v === null || v === undefined || Number.isNaN(v)
    ? '—'
    : `${v > 0 ? '+' : ''}${MW(v, digits)}`
