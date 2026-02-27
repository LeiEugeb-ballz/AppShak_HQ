function formatValue(value) {
  if (value === null || value === undefined) {
    return 'n/a'
  }
  return String(value)
}

export function StatusPanel({ snapshot, isOnline, error, lastUpdated }) {
  const running = Boolean(snapshot?.running)
  const indicatorClass = running ? 'status-panel__indicator status-panel__indicator--running' : 'status-panel__indicator'

  return (
    <section className="panel status-panel">
      <header className="panel__header">
        <h2>Status</h2>
        <span className={indicatorClass} aria-label={running ? 'running' : 'not running'} />
      </header>

      <div className="status-grid">
        <div className="status-item">
          <span className="status-item__label">running</span>
          <span className="status-item__value">{String(running)}</span>
        </div>
        <div className="status-item">
          <span className="status-item__label">event_queue_size</span>
          <span className="status-item__value">{formatValue(snapshot?.event_queue_size)}</span>
        </div>
        <div className="status-item">
          <span className="status-item__label">timestamp</span>
          <span className="status-item__value">{formatValue(snapshot?.timestamp)}</span>
        </div>
        <div className="status-item">
          <span className="status-item__label">backend_online</span>
          <span className="status-item__value">{String(isOnline)}</span>
        </div>
      </div>

      <div className="status-block">
        <span className="status-item__label">current_event</span>
        <pre>{JSON.stringify(snapshot?.current_event, null, 2)}</pre>
      </div>

      <div className="status-meta">
        <span>last_snapshot_update: {formatValue(lastUpdated)}</span>
        <span>snapshot_error: {formatValue(error)}</span>
      </div>
    </section>
  )
}

