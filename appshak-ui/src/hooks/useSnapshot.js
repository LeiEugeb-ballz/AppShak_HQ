import { useEffect, useState } from 'react'

const SNAPSHOT_URL = '/api/snapshot'
const POLL_INTERVAL_MS = 2000

function normalizeSnapshot(raw) {
  const input = raw && typeof raw === 'object' ? raw : {}
  const currentEvent =
    input.current_event && typeof input.current_event === 'object'
      ? input.current_event
      : null

  return {
    running: Boolean(input.running),
    event_queue_size: Number.isFinite(Number(input.event_queue_size))
      ? Number(input.event_queue_size)
      : 0,
    current_event: currentEvent,
    timestamp: typeof input.timestamp === 'string' ? input.timestamp : null,
  }
}

export function useSnapshot() {
  const [snapshot, setSnapshot] = useState(() =>
    normalizeSnapshot({
      running: false,
      event_queue_size: 0,
      current_event: null,
      timestamp: null,
    }),
  )
  const [isOnline, setIsOnline] = useState(false)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  useEffect(() => {
    let isDisposed = false
    let requestInFlight = false

    const pollSnapshot = async () => {
      if (requestInFlight || isDisposed) {
        return
      }
      requestInFlight = true
      try {
        const response = await fetch(SNAPSHOT_URL, { cache: 'no-store' })
        if (!response.ok) {
          throw new Error(`Snapshot request failed (${response.status})`)
        }
        const data = await response.json()
        if (isDisposed) {
          return
        }
        setSnapshot(normalizeSnapshot(data))
        setIsOnline(true)
        setError(null)
        setLastUpdated(new Date().toISOString())
      } catch (err) {
        if (isDisposed) {
          return
        }
        setIsOnline(false)
        setError(err instanceof Error ? err.message : 'Snapshot backend offline')
      } finally {
        requestInFlight = false
      }
    }

    pollSnapshot()
    const timer = setInterval(pollSnapshot, POLL_INTERVAL_MS)

    return () => {
      isDisposed = true
      clearInterval(timer)
    }
  }, [])

  return {
    snapshot,
    isOnline,
    error,
    lastUpdated,
  }
}

