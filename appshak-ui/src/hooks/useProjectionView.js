import { useEffect, useRef, useState } from 'react'

const SNAPSHOT_URL = '/api/snapshot'

function resolveEventsUrl() {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProtocol}//${window.location.host}/ws/events`
}

const EVENTS_URL = resolveEventsUrl()

const SNAPSHOT_POLL_MS = 2000
const RECONNECT_BASE_MS = 600
const RECONNECT_MAX_MS = 12000
const SIGNAL_LOST_THRESHOLD_MS = 6500

function isRecord(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function toSafeNumber(value, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function sanitizeCurrentEvent(value) {
  if (value === null) {
    return null
  }
  if (!isRecord(value)) {
    return null
  }
  return {
    type: typeof value.type === 'string' && value.type.length > 0 ? value.type : null,
    origin_id: typeof value.origin_id === 'string' && value.origin_id.length > 0 ? value.origin_id : null,
    timestamp:
      typeof value.timestamp === 'string' && value.timestamp.length > 0
        ? value.timestamp
        : new Date().toISOString(),
  }
}

function sanitizeEventTypeCounts(value) {
  if (!isRecord(value)) {
    return {}
  }
  const output = {}
  for (const [key, count] of Object.entries(value)) {
    const parsed = Number(count)
    if (Number.isFinite(parsed)) {
      output[String(key)] = parsed
    }
  }
  return output
}

function createDefaultView() {
  return {
    schema_version: 1,
    timestamp: null,
    last_updated_at: null,
    running: false,
    event_queue_size: 0,
    current_event: null,
    event_type_counts: {},
    tool_audit_counts: {
      allowed: 0,
      denied: 0,
    },
  }
}

function mergeProjectionView(previous, raw) {
  const next = { ...previous }
  if (!isRecord(raw)) {
    return next
  }
  const hasOwn = Object.prototype.hasOwnProperty

  if (hasOwn.call(raw, 'schema_version')) {
    const parsed = Number(raw.schema_version)
    next.schema_version = Number.isFinite(parsed) ? parsed : null
  }

  if (hasOwn.call(raw, 'timestamp')) {
    next.timestamp = typeof raw.timestamp === 'string' && raw.timestamp.length > 0 ? raw.timestamp : null
  }

  if (hasOwn.call(raw, 'last_updated_at')) {
    next.last_updated_at =
      typeof raw.last_updated_at === 'string' && raw.last_updated_at.length > 0
        ? raw.last_updated_at
        : null
  }

  if (hasOwn.call(raw, 'running')) {
    next.running = Boolean(raw.running)
  }

  if (hasOwn.call(raw, 'event_queue_size')) {
    next.event_queue_size = Math.max(0, toSafeNumber(raw.event_queue_size, previous.event_queue_size))
  }

  if (hasOwn.call(raw, 'current_event')) {
    next.current_event = sanitizeCurrentEvent(raw.current_event)
  }

  if (hasOwn.call(raw, 'event_type_counts')) {
    next.event_type_counts = sanitizeEventTypeCounts(raw.event_type_counts)
  }

  if (hasOwn.call(raw, 'tool_audit_counts')) {
    const counts = isRecord(raw.tool_audit_counts) ? raw.tool_audit_counts : {}
    const previousCounts = previous.tool_audit_counts ?? { allowed: 0, denied: 0 }
    next.tool_audit_counts = {
      allowed: Math.max(
        0,
        toSafeNumber(
          Object.prototype.hasOwnProperty.call(counts, 'allowed') ? counts.allowed : previousCounts.allowed,
          previousCounts.allowed,
        ),
      ),
      denied: Math.max(
        0,
        toSafeNumber(
          Object.prototype.hasOwnProperty.call(counts, 'denied') ? counts.denied : previousCounts.denied,
          previousCounts.denied,
        ),
      ),
    }
  }

  return next
}

function extractViewPayload(rawMessage) {
  if (!isRecord(rawMessage) || rawMessage.channel !== 'view_update') {
    return null
  }
  if (isRecord(rawMessage.data) && isRecord(rawMessage.data.view)) {
    return rawMessage.data.view
  }
  if (isRecord(rawMessage.view)) {
    return rawMessage.view
  }
  if (isRecord(rawMessage.data)) {
    return rawMessage.data
  }
  return null
}

function extractTimestampCandidate(raw) {
  if (!isRecord(raw)) {
    return null
  }
  if (typeof raw.last_updated_at === 'string' && raw.last_updated_at.length > 0) {
    return raw.last_updated_at
  }
  if (typeof raw.timestamp === 'string' && raw.timestamp.length > 0) {
    return raw.timestamp
  }
  return null
}

export function useProjectionView() {
  const [view, setView] = useState(() => createDefaultView())
  const [connectionState, setConnectionState] = useState('connecting')
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [signalLost, setSignalLost] = useState(false)
  const [isOnline, setIsOnline] = useState(false)

  const schemaWarnedRef = useRef(false)
  const lastSuccessAtRef = useRef(Date.now())

  useEffect(() => {
    let disposed = false
    let reconnectTimer = null
    let socket = null
    let reconnectAttempt = 0
    let hasConnectedAtLeastOnce = false
    let snapshotInFlight = false
    let wsConnected = false

    const applyIncomingView = (payload, updateTimestamp) => {
      setView((previous) => {
        const merged = mergeProjectionView(previous, payload)
        if (
          merged.schema_version !== null &&
          merged.schema_version !== 1 &&
          !schemaWarnedRef.current
        ) {
          schemaWarnedRef.current = true
          console.warn(
            `[OfficeView] Unexpected schema_version=${String(merged.schema_version)}; rendering with compatibility fallback.`,
          )
        }
        return merged
      })

      if (updateTimestamp) {
        const timestamp = extractTimestampCandidate(payload) ?? new Date().toISOString()
        setLastUpdated(timestamp)
      }

      lastSuccessAtRef.current = Date.now()
      setSignalLost(false)
      setIsOnline(true)
      setError(null)
    }

    const pollSnapshot = async () => {
      if (disposed || snapshotInFlight) {
        return
      }
      snapshotInFlight = true
      try {
        const response = await fetch(SNAPSHOT_URL, { cache: 'no-store' })
        if (!response.ok) {
          throw new Error(`Snapshot request failed (${response.status})`)
        }
        const payload = await response.json()
        if (disposed) {
          return
        }
        applyIncomingView(payload, true)
      } catch (err) {
        if (disposed) {
          return
        }
        if (!wsConnected) {
          setError(err instanceof Error ? err.message : 'Projection snapshot backend offline')
        }
      } finally {
        snapshotInFlight = false
      }
    }

    const scheduleReconnect = () => {
      if (disposed) {
        return
      }
      const delay = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt))
      reconnectAttempt += 1
      reconnectTimer = setTimeout(connect, delay)
    }

    const connect = () => {
      if (disposed) {
        return
      }

      setConnectionState(hasConnectedAtLeastOnce ? 'reconnecting' : 'connecting')
      socket = new WebSocket(EVENTS_URL)

      socket.onopen = () => {
        if (disposed) {
          return
        }
        wsConnected = true
        hasConnectedAtLeastOnce = true
        reconnectAttempt = 0
        setConnectionState('connected')
      }

      socket.onmessage = (message) => {
        if (disposed) {
          return
        }
        try {
          const parsed = JSON.parse(message.data)
          const viewPayload = extractViewPayload(parsed)
          if (!viewPayload) {
            return
          }
          applyIncomingView(viewPayload, true)
        } catch {
          // Ignore malformed websocket payloads.
        }
      }

      socket.onerror = () => {
        if (disposed) {
          return
        }
        setError('Projection event stream error')
      }

      socket.onclose = () => {
        if (disposed) {
          return
        }
        wsConnected = false
        setConnectionState('disconnected')
        scheduleReconnect()
      }
    }

    connect()
    pollSnapshot()

    const pollTimer = setInterval(pollSnapshot, SNAPSHOT_POLL_MS)
    const healthTimer = setInterval(() => {
      if (disposed) {
        return
      }
      const lost = Date.now() - lastSuccessAtRef.current > SIGNAL_LOST_THRESHOLD_MS
      setSignalLost(lost)
      setIsOnline(!lost)
    }, 1000)

    return () => {
      disposed = true
      clearInterval(pollTimer)
      clearInterval(healthTimer)
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
      if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
        socket.close()
      }
    }
  }, [])

  return {
    view,
    connectionState,
    error,
    lastUpdated,
    signalLost,
    isOnline,
  }
}
