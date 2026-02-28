import { EventConsole } from '../components/EventConsole'
import { StatusPanel } from '../components/StatusPanel'
import { useEventStream } from '../hooks/useEventStream'
import { useSnapshot } from '../hooks/useSnapshot'

export function SummaryView() {
  const { snapshot, isOnline, error: snapshotError, lastUpdated } = useSnapshot()
  const {
    events,
    connectionState,
    error: streamError,
    lastEventAt,
  } = useEventStream()

  return (
    <div className="dashboard__grid">
      <StatusPanel
        snapshot={snapshot}
        isOnline={isOnline}
        error={snapshotError}
        lastUpdated={lastUpdated}
      />
      <EventConsole
        events={events}
        connectionState={connectionState}
        error={streamError}
        lastEventAt={lastEventAt}
      />
    </div>
  )
}
