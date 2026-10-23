import { useEffect, useState } from 'react'

// Shown once, on a first visit. Written for someone who trades power and has
// never seen this tool: no statistics vocabulary, no mention of endpoints.

const KEY = 'headroom.howto.dismissed.v1'

export default function HowToRead() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    // Storage can throw in a locked-down browser; a missing flag just means
    // the panel shows, which is the safe direction.
    try {
      setOpen(localStorage.getItem(KEY) !== '1')
    } catch {
      setOpen(true)
    }
  }, [])

  const dismiss = () => {
    setOpen(false)
    try {
      localStorage.setItem(KEY, '1')
    } catch {
      /* nothing to do: the panel simply returns next visit */
    }
  }

  if (!open) return null

  return (
    <section className="howto" aria-labelledby="howto-title">
      <div className="howto-head">
        <h2 id="howto-title">How to read this</h2>
        <button className="ghost-btn" type="button" onClick={dismiss}>
          Got it
        </button>
      </div>

      <ol className="howto-steps">
        <li>
          <strong>The white line is what the wind actually did.</strong> The
          dashed blue line is what the forecast said it would do — using only
          what had been published before the auction closed.
        </li>
        <li>
          <strong>The gap between them is your exposure.</strong> When the
          dashed line sits above the white one, the forecast promised wind that
          never turned up, and someone had to buy the difference.
        </li>
        <li>
          <strong>The shaded band is how wrong it usually is</strong> at this
          notice period, measured from its own past misses. Wind lands inside
          that band about four times in five.
        </li>
        <li>
          <strong>Plan tells you one number to commit to.</strong> Pick how
          certain you want to be, and it tells you the megawatts you can count
          on. Ask for more certainty and the number drops.
        </li>
        <li>
          <strong>Decision Replay shows a single day unfolding.</strong> Drag the
          slider to any moment and you see exactly the forecast that was on
          screen then — the actual stays hidden until the slider reaches it,
          because that is when you would have known.
        </li>
      </ol>

      <p className="howto-foot">
        Everything is national GB wind in megawatts, times in UTC. Nothing
        published after a cutoff is ever used before it.
      </p>
    </section>
  )
}
