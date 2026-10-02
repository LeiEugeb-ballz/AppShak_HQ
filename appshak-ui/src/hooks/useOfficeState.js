import { useEffect, useMemo, useState } from 'react'
import { buildOfficeViewModel, mapCanonicalOfficeState } from '../office/officeState'

const OFFICE_URL = '/api/office/state'
const POLL_MS = 2000
const REQUEST_TIMEOUT_MS = 5000

export function useOfficeState() {
  const [canonicalState, setCanonicalState] = useState(null)
  const [receivedAt, setReceivedAt] = useState(null)
  const [errorKind, setErrorKind] = useState(null)
  const [errorMessage, setErrorMessage] = useState(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    let disposed = false
    let inFlight = false
    let controller = null

    const poll = async () => {
      if (disposed || inFlight) return
      inFlight = true
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
      try {
        const response = await fetch(OFFICE_URL, {
          method: 'GET',
          cache: 'no-store',
          signal: controller.signal,
        })
        if (!response.ok) {
          const kind = response.status === 502 || response.status === 504
            ? 'BACKEND_UNAVAILABLE' : 'PROJECTION_ERROR'
          const failure = new Error(`Office state request failed (${response.status})`)
          failure.officeKind = kind
          throw failure
        }
        const next = mapCanonicalOfficeState(await response.json())
        if (disposed) return
        const observedAt = Date.now()
        setCanonicalState(next)
        setReceivedAt(observedAt)
        setNow(observedAt)
        setErrorKind(null)
        setErrorMessage(null)
      } catch (error) {
        if (disposed) return
        setErrorKind(error?.officeKind ?? (
          error instanceof TypeError || error?.name === 'AbortError'
            ? 'BACKEND_UNAVAILABLE' : 'PROJECTION_ERROR'
        ))
        setErrorMessage(error instanceof Error ? error.message : 'Office state unavailable')
      } finally {
        clearTimeout(timeout)
        inFlight = false
        controller = null
      }
    }

    poll()
    const pollTimer = setInterval(poll, POLL_MS)
    const freshnessTimer = setInterval(() => setNow(Date.now()), 1000)
    return () => {
      disposed = true
      clearInterval(pollTimer)
      clearInterval(freshnessTimer)
      controller?.abort()
    }
  }, [])

  return useMemo(() => buildOfficeViewModel(canonicalState, {
    receivedAt, now, errorKind, errorMessage,
  }), [canonicalState, receivedAt, now, errorKind, errorMessage])
}
