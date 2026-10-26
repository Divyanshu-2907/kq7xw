// How the hero card judges its own calibration.
//
// Missing the target is not symmetric. Covering more often than promised costs
// a little margin and nothing else. Covering less often means the plan was
// optimistic, the wind did not arrive, and someone bought the gap at whatever
// the market was charging. Only that direction is flagged.

const OPTIMISTIC_TOLERANCE_PP = 1
const OPTIMISTIC_SERIOUS_PP = 5

export function gradeShortfall(shortfallPct, targetPct) {
  if (shortfallPct == null || targetPct == null) return null
  const over = shortfallPct - targetPct // positive = short more often than promised
  if (over < OPTIMISTIC_TOLERANCE_PP) return { tone: 'on-target', label: null, over }
  const pp = `+${over.toFixed(1)} pp`
  if (over <= OPTIMISTIC_SERIOUS_PP) {
    return { tone: 'off-target', label: `slightly optimistic (${pp})`, over }
  }
  return { tone: 'off-target-bad', label: `optimistic (${pp})`, over }
}
