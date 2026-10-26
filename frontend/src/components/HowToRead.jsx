import { useEffect, useRef } from 'react'

// Explanation, on request. It opens from the header button, and on a genuine
// first visit it appears once as a popover anchored to that button rather than
// a full-width panel, so it never pushes the chart off the first screen.

const KEY = 'headroom.howto.dismissed.v1'

export function hasSeenHowTo() {
  // Storage throws in a locked-down browser; treating that as "not seen" shows
  // the popover, which is the harmless direction.
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

export function markHowToSeen() {
  try {
    localStorage.setItem(KEY, '1')
  } catch {
    /* nothing to do: it simply reappears next visit */
  }
}

export default function HowToRead({ onClose }) {
  const ref = useRef(null)

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose()
    }
    window.addEventListener('keydown', onKey)
    // Defer: the click that opened this would otherwise close it immediately.
    const id = setTimeout(() => window.addEventListener('mousedown', onClick), 0)
    return () => {
      clearTimeout(id)
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onClick)
    }
  }, [onClose])

  return (
    <>
      <div className="howto-scrim" aria-hidden="true" />
      <div
        className="howto-pop"
        role="dialog"
        aria-labelledby="howto-title"
        ref={ref}
      >
        <div className="howto-head">
          <h2 id="howto-title">How to read this</h2>
          <button
            className="ghost-btn"
            type="button"
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <ol className="howto-steps">
          <li>
            <strong>The white line is what the wind actually did.</strong> The
            dashed blue line is what the forecast said — using only what had been
            published before the auction closed.
          </li>
          <li>
            <strong>The gap between them is your exposure.</strong> When the
            dashed line sits above the white one, the forecast promised wind that
            never turned up.
          </li>
          <li>
            <strong>The shaded band is how wrong it usually is</strong> at this
            notice period, measured from its own past misses. Wind lands inside
            it about four times in five.
          </li>
          <li>
            <strong>&ldquo;Plan on&rdquo; is the number to commit to.</strong>{' '}
            Pick how certain you want to be; ask for more certainty and the
            number drops.
          </li>
          <li>
            <strong>Decision Replay shows a day unfolding.</strong> Drag the
            slider and you see the forecast that was on screen at that moment —
            the actual stays hidden until the slider reaches it.
          </li>
        </ol>

        <p className="howto-foot">
          National GB wind, megawatts, times UTC. Nothing published after a
          cutoff is ever used before it.
        </p>

        <button className="ghost-btn howto-got-it" type="button" onClick={onClose}>
          Got it
        </button>
      </div>
    </>
  )
}
