// Loading, empty and error states. All three say what is happening in words a
// trader can act on, rather than a spinner or a stack trace.

export function Info({ children }) {
  return (
    <span className="info" tabIndex={0} role="note">
      i<span className="info-body">{children}</span>
    </span>
  )
}

export function Skeleton({ height = 16, width = '100%', style }) {
  return <div className="skeleton" style={{ height, width, ...style }} aria-hidden="true" />
}

export function ChartSkeleton({ height = 280 }) {
  return (
    <div aria-busy="true" aria-live="polite">
      <Skeleton height={height} />
    </div>
  )
}

export function CardsSkeleton({ count = 4 }) {
  return (
    <div className="cards" aria-busy="true">
      {Array.from({ length: count }, (_, i) => (
        <div className="card" key={i}>
          <Skeleton height={9} width="52%" />
          <Skeleton height={21} width="68%" style={{ marginTop: 8 }} />
          <Skeleton height={9} width="84%" style={{ marginTop: 7 }} />
        </div>
      ))}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  const isNetwork = error?.status === 0
  const isValidation = error?.status === 422
  const title = isNetwork
    ? 'Cannot reach the API'
    : isValidation
      ? 'That selection is not available'
      : 'Something went wrong'
  return (
    <div className="state error" role="alert">
      <div className="state-title">{title}</div>
      <div className="state-detail">{error?.message ?? String(error)}</div>
      {isNetwork && (
        <div className="state-detail">
          Start the backend with <code>uvicorn app.main:app --port 8000</code> from{' '}
          <code>backend/</code>, or point <code>VITE_API_BASE</code> at a running one.
        </div>
      )}
      {onRetry && (
        <button className="ghost-btn" onClick={onRetry} type="button">
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title = 'Nothing to show', detail }) {
  return (
    <div className="state">
      <div className="state-title">{title}</div>
      {detail && <div className="state-detail">{detail}</div>}
    </div>
  )
}
