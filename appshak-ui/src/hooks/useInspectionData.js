import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

const API_ENTITIES = '/api/inspect/entities'
const API_ENTITY = '/api/inspect/entity'
const API_OFFICE_TIMELINE = '/api/inspect/office/timeline'
const API_INTEGRITY_LATEST = '/api/integrity/latest'
const API_STABILITY_RUNS = '/api/stability/runs'
const DEFAULT_PAGE_LIMIT = 25

function resolveEventsUrl() {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProtocol}//${window.location.host}/ws/events`
}

function eventKey(event) {
  const source = typeof event?.source === 'string' ? event.source : 'unknown'
  const entryType = typeof event?.entry_type === 'string' ? event.entry_type : 'unknown'
  const eventId = Number.isFinite(Number(event?.event_id)) ? Number(event.event_id) : -1
  const seq = Number.isFinite(Number(event?.seq)) ? Number(event.seq) : -1
  const timestamp = typeof event?.timestamp === 'string' ? event.timestamp : 'na'
  return `${source}:${entryType}:${eventId}:${seq}:${timestamp}`
}

function mergeUniqueEvents(previousItems, incomingItems) {
  const seen = new Set(previousItems.map(eventKey))
  const merged = [...previousItems]
  for (const item of incomingItems) {
    const key = eventKey(item)
    if (seen.has(key)) {
      continue
    }
    seen.add(key)
    merged.push(item)
  }
  return merged
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`Request failed (${response.status}) for ${url}`)
  }
  return response.json()
}

export function useInspectionData() {
  const [entities, setEntities] = useState([])
  const [selectedEntityId, setSelectedEntityId] = useState(null)
  const [selectedEntity, setSelectedEntity] = useState(null)
  const [entityTimeline, setEntityTimeline] = useState({ items: [], next_cursor: null, total: 0 })
  const [officeTimeline, setOfficeTimeline] = useState({ items: [], next_cursor: null, total: 0 })
  const [integrityLatest, setIntegrityLatest] = useState({})
  const [stabilityRuns, setStabilityRuns] = useState([])
  const [error, setError] = useState(null)
  const [connectionState, setConnectionState] = useState('connecting')

  const reconnectRef = useRef(null)
  const socketRef = useRef(null)

  const fetchEntities = useCallback(async () => {
    const payload = await fetchJson(API_ENTITIES)
    const next = Array.isArray(payload?.items) ? payload.items : []
    setEntities(next)
    if (!selectedEntityId && next.length > 0) {
      setSelectedEntityId(next[0].id ?? null)
    }
  }, [selectedEntityId])

  const fetchIntegrity = useCallback(async () => {
    const payload = await fetchJson(API_INTEGRITY_LATEST)
    setIntegrityLatest(payload && typeof payload === 'object' ? payload : {})
  }, [])

  const fetchStabilityRuns = useCallback(async () => {
    const payload = await fetchJson(API_STABILITY_RUNS)
    const next = Array.isArray(payload?.items) ? payload.items : []
    setStabilityRuns(next)
  }, [])

  const fetchEntity = useCallback(async (entityId) => {
    if (!entityId) {
      setSelectedEntity(null)
      return
    }
    const payload = await fetchJson(`${API_ENTITY}/${encodeURIComponent(entityId)}`)
    setSelectedEntity(payload && typeof payload === 'object' ? payload : null)
  }, [])

  const fetchEntityTimeline = useCallback(async (entityId, cursor = null) => {
    if (!entityId) {
      setEntityTimeline({ items: [], next_cursor: null, total: 0 })
      return
    }
    const query = new URLSearchParams({
      limit: String(DEFAULT_PAGE_LIMIT),
    })
    if (typeof cursor === 'string' && cursor.length > 0) {
      query.set('cursor', cursor)
    }
    const payload = await fetchJson(
      `${API_ENTITY}/${encodeURIComponent(entityId)}/timeline?${query.toString()}`,
    )
    const incomingItems = Array.isArray(payload?.items) ? payload.items : []
    setEntityTimeline((previous) => {
      const base = cursor ? previous.items : []
      return {
        items: mergeUniqueEvents(base, incomingItems),
        next_cursor: typeof payload?.next_cursor === 'string' ? payload.next_cursor : null,
        total: Number.isFinite(Number(payload?.total)) ? Number(payload.total) : incomingItems.length,
      }
    })
  }, [])

  const fetchOfficeTimeline = useCallback(async (cursor = null) => {
    const query = new URLSearchParams({
      limit: String(DEFAULT_PAGE_LIMIT),
    })
    if (typeof cursor === 'string' && cursor.length > 0) {
      query.set('cursor', cursor)
    }
    const payload = await fetchJson(`${API_OFFICE_TIMELINE}?${query.toString()}`)
    const incomingItems = Array.isArray(payload?.items) ? payload.items : []
    setOfficeTimeline((previous) => {
      const base = cursor ? previous.items : []
      return {
        items: mergeUniqueEvents(base, incomingItems),
        next_cursor: typeof payload?.next_cursor === 'string' ? payload.next_cursor : null,
        total: Number.isFinite(Number(payload?.total)) ? Number(payload.total) : incomingItems.length,
      }
    })
  }, [])

  const refreshAll = useCallback(async () => {
    try {
      await Promise.all([fetchEntities(), fetchIntegrity(), fetchStabilityRuns(), fetchOfficeTimeline(null)])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Inspection fetch failed')
    }
  }, [fetchEntities, fetchIntegrity, fetchOfficeTimeline, fetchStabilityRuns])

  useEffect(() => {
    refreshAll()
  }, [refreshAll])

  useEffect(() => {
    if (!selectedEntityId) {
      setSelectedEntity(null)
      setEntityTimeline({ items: [], next_cursor: null, total: 0 })
      return
    }
    let disposed = false
    const run = async () => {
      try {
        await Promise.all([fetchEntity(selectedEntityId), fetchEntityTimeline(selectedEntityId, null)])
      } catch (err) {
        if (!disposed) {
          setError(err instanceof Error ? err.message : 'Entity fetch failed')
        }
      }
    }
    run()
    return () => {
      disposed = true
    }
  }, [fetchEntity, fetchEntityTimeline, selectedEntityId])

  useEffect(() => {
    let disposed = false

    const scheduleReconnect = () => {
      if (disposed) {
        return
      }
      reconnectRef.current = setTimeout(connect, 1500)
    }

    const connect = () => {
      if (disposed) {
        return
      }
      setConnectionState((previous) => (previous === 'connected' ? 'reconnecting' : 'connecting'))
      const socket = new WebSocket(resolveEventsUrl())
      socketRef.current = socket

      socket.onopen = () => {
        if (disposed) {
          return
        }
        setConnectionState('connected')
      }

      socket.onmessage = (message) => {
        if (disposed) {
          return
        }
        try {
          const payload = JSON.parse(message.data)
          const channel = payload?.channel
          if (channel === 'inspect_update') {
            refreshAll()
          } else if (channel === 'integrity_update') {
            fetchIntegrity()
          }
        } catch {
          // Ignore malformed payloads.
        }
      }

      socket.onerror = () => {
        if (disposed) {
          return
        }
        setConnectionState('error')
      }

      socket.onclose = () => {
        if (disposed) {
          return
        }
        setConnectionState('disconnected')
        scheduleReconnect()
      }
    }

    connect()
    return () => {
      disposed = true
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current)
      }
      if (
        socketRef.current &&
        (socketRef.current.readyState === WebSocket.OPEN ||
          socketRef.current.readyState === WebSocket.CONNECTING)
      ) {
        socketRef.current.close()
      }
    }
  }, [fetchIntegrity, refreshAll])

  const selectedEntityType = useMemo(() => {
    const value = selectedEntity?.entity_type
    return typeof value === 'string' ? value : 'agent'
  }, [selectedEntity])

  return {
    entities,
    selectedEntityId,
    setSelectedEntityId,
    selectedEntity,
    selectedEntityType,
    entityTimeline,
    officeTimeline,
    integrityLatest,
    stabilityRuns,
    error,
    connectionState,
    loadMoreEntityTimeline: () => {
      if (selectedEntityId && entityTimeline.next_cursor) {
        fetchEntityTimeline(selectedEntityId, entityTimeline.next_cursor)
      }
    },
    loadMoreOfficeTimeline: () => {
      if (officeTimeline.next_cursor) {
        fetchOfficeTimeline(officeTimeline.next_cursor)
      }
    },
    refreshAll,
  }
}
