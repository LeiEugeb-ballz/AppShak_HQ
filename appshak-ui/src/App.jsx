import { useEffect, useState } from 'react'
import './App.css'
import { OfficeView } from './views/OfficeView'
import { SummaryView } from './views/SummaryView'

const ROUTE_SUMMARY = 'summary'
const ROUTE_OFFICE = 'office'

function routeToHash(route) {
  return `#/${route}`
}

function readRouteFromHash() {
  const parsed = window.location.hash.replace(/^#\/?/, '').trim().toLowerCase()
  return parsed === ROUTE_OFFICE ? ROUTE_OFFICE : ROUTE_SUMMARY
}

function navLinkClass(active) {
  return active ? 'dashboard__nav-link dashboard__nav-link--active' : 'dashboard__nav-link'
}

function App() {
  const [route, setRoute] = useState(() => readRouteFromHash())

  useEffect(() => {
    const onHashChange = () => {
      setRoute(readRouteFromHash())
    }
    if (!window.location.hash) {
      window.location.hash = routeToHash(ROUTE_SUMMARY)
    }
    window.addEventListener('hashchange', onHashChange)
    return () => {
      window.removeEventListener('hashchange', onHashChange)
    }
  }, [])

  return (
    <main className="dashboard">
      <header className="dashboard__header">
        <div>
          <h1>AppShak Observability</h1>
          <p>Backend: http://127.0.0.1:8010</p>
        </div>
        <nav className="dashboard__nav" aria-label="Observability views">
          <a className={navLinkClass(route === ROUTE_SUMMARY)} href={routeToHash(ROUTE_SUMMARY)}>
            Summary View
          </a>
          <a className={navLinkClass(route === ROUTE_OFFICE)} href={routeToHash(ROUTE_OFFICE)}>
            Office View
          </a>
        </nav>
      </header>
      {route === ROUTE_OFFICE ? <OfficeView /> : <SummaryView />}
    </main>
  )
}

export default App
