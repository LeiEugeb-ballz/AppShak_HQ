import './App.css'
import { EventConsole } from './components/EventConsole'
import { StatusPanel } from './components/StatusPanel'
import { useEventStream } from './hooks/useEventStream'
import { useSnapshot } from './hooks/useSnapshot'

function App() {
  const { snapshot, isOnline, error: snapshotError, lastUpdated } = useSnapshot()
  const {
    events,
    connectionState,
    error: streamError,
    lastEventAt,
  } = useEventStream()

  return (
    <main className="dashboard">
      <header className="dashboard__header">
        <h1>AppShak Observability</h1>
        <p>Backend: http://127.0.0.1:8010</p>
      </header>
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
    </main>
  )
}

export default App
