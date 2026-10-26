import { useEffect, useState } from 'react'

// Charts need a numeric height, so the breakpoint has to be readable from JS
// as well as from CSS. Kept in one place so the two cannot drift.
export const NARROW_PX = 620

export function useIsNarrow() {
  const [narrow, setNarrow] = useState(
    () => typeof window !== 'undefined' && window.innerWidth <= NARROW_PX,
  )

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${NARROW_PX}px)`)
    const onChange = (e) => setNarrow(e.matches)
    setNarrow(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  return narrow
}
