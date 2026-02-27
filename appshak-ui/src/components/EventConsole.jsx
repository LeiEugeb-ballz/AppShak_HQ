import { useEffect, useMemo, useRef } from 'react'

function eventTypeFromRecord(record) {
  const fromEvent = record?.data?.event?.type
  if (typeof fromEvent === 'string' && fromEvent.length > 0) {
    return fromEvent
  }
  const fromAudit = record?.data?.audit?.action_type
  if (typeof fromAudit === 'string' && fromAudit.length > 0) {
    return fromAudit
  }
  return 'UNKNOWN'
}

function eventClassName(type) {
  const upper = type.toUpperCase()
  if (upper.includes('WORKER') || upper.includes('SUPERVISOR') || upper.includes('AGENT_STATUS')) {
    return 'event-row event-row--worker'
  }
  if (upper.includes('TOOL')) {
    return 'event-row event-row--tool'
  }
  if (upper.includes('INTENT')) {
    return 'event-row event-row--intent'
  }
  if (upper.includes('PROPOSAL') || upper.includes('PLUGIN')) {
    return 'event-row event-row--plugin'
  }
  return 'event-row event-row--default'
}

export function EventConsole({ events, connectionState, error, lastEventAt }) {
  const scrollRef = useRef(null)
  const renderedEvents = useMemo(() => events ?? [], [events])

  useEffect(() => {
    const node = scrollRef.current
    if (!node) {
      return
    }
    node.scrollTop = node.scrollHeight
  }, [renderedEvents.length])

  return (
    <section className="panel event-console">
      <header className="panel__header">
        <h2>Event Console</h2>
        <span className="event-console__meta">
          state: {connectionState} | events: {renderedEvents.length}
        </span>
      </header>

      <div className="event-console__meta event-console__meta--secondary">
        <span>last_event_at: {lastEventAt ?? 'n/a'}</span>
        <span>stream_error: {error ?? 'n/a'}</span>
      </div>

      <div className="event-console__list" ref={scrollRef}>
        {renderedEvents.length === 0 ? (
          <div className="event-empty">No events received yet.</div>
        ) : (
          renderedEvents.map((event, index) => {
            const type = eventTypeFromRecord(event)
            return (
              <article key={`${event.timestamp}-${index}`} className={eventClassName(type)}>
                <div className="event-row__head">
                  <span>{event.timestamp}</span>
                  <span>{event.channel}</span>
                  <span>{type}</span>
                  <span>{event.source}</span>
                </div>
                <pre>{JSON.stringify(event.data, null, 2)}</pre>
              </article>
            )
          })
        )}
      </div>
    </section>
  )
}

