import { useEffect, useState } from 'react'

function resolveEventsUrl() {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProtocol}//${window.location.host}/ws/events`
}

const EVENTS_URL = resolveEventsUrl()
const RECONNECT_DELAY_MS = 2000
const MAX_EVENTS = 200

function normalizeEvent(raw) {
  const input = raw && typeof raw === 'object' ? raw : {}
  return {
    channel: typeof input.channel === 'string' ? input.channel : 'unknown',
    timestamp: typeof input.timestamp === 'string' ? input.timestamp : new Date().toISOString(),
    source: typeof input.source === 'string' ? input.source : 'unknown',
    data: input.data && typeof input.data === 'object' ? input.data : {},
  }
}

export function useEventStream() {
  const [events, setEvents] = useState([])
  const [connectionState, setConnectionState] = useState('connecting')
  const [error, setError] = useState(null)
  const [lastEventAt, setLastEventAt] = useState(null)

  useEffect(() => {
    let socket = null
    let reconnectTimer = null
    let disposed = false

    const connect = () => {
      if (disposed) {
        return
      }
      setConnectionState((current) => (current === 'connected' ? 'reconnecting' : 'connecting'))

      socket = new WebSocket(EVENTS_URL)

      socket.onopen = () => {
        if (disposed) {
          return
        }
        setConnectionState('connected')
        setError(null)
      }

      socket.onmessage = (message) => {
        if (disposed) {
          return
        }
        try {
          const parsed = JSON.parse(message.data)
          const normalized = normalizeEvent(parsed)
          setEvents((prev) => {
            const next = [...prev, normalized]
            return next.length > MAX_EVENTS ? next.slice(next.length - MAX_EVENTS) : next
          })
          setLastEventAt(new Date().toISOString())
        } catch {
          // Ignore malformed websocket payloads.
        }
      }

      socket.onerror = () => {
        if (disposed) {
          return
        }
        setError('Event stream error')
      }

      socket.onclose = () => {
        if (disposed) {
          return
        }
        setConnectionState('disconnected')
        reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS)
      }
    }

    connect()

    return () => {
      disposed = true
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
      if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
        socket.close()
      }
    }
  }, [])

  return {
    events,
    connectionState,
    error,
    lastEventAt,
  }
}

