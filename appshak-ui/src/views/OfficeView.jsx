import { useEffect, useRef } from 'react'
import { useInspectionData } from '../hooks/useInspectionData'
import { useProjectionView } from '../hooks/useProjectionView'
import { OfficeAnimator } from '../office/animator'
import { createOfficeSceneRenderer } from '../office/scene'

function formatTimestamp(value) {
  if (typeof value !== 'string' || value.length === 0) {
    return 'n/a'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

function queueValue(view) {
  const parsed = Number(view?.event_queue_size)
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0
}

function renderEntityDetail(label, value) {
  return (
    <div className="office-view__detail-row" key={label}>
      <span className="office-view__detail-label">{label}</span>
      <span className="office-view__detail-value">{String(value ?? 'n/a')}</span>
    </div>
  )
}

function TimelineBlock({ title, timeline, onLoadMore }) {
  return (
    <section className="panel office-view__timeline-panel">
      <header className="panel__header">
        <h2>{title}</h2>
      </header>
      <div className="office-view__timeline-list">
        {timeline.items.length === 0 ? (
          <p className="event-empty">No events yet.</p>
        ) : (
          timeline.items.map((event, index) => (
            <div className="event-row event-row--default" key={`${event.source ?? 'src'}-${index}`}>
              <div className="event-row__head">
                <span>{String(event.entry_type ?? 'UNKNOWN')}</span>
                <span>{String(event.source ?? 'unknown')}</span>
                <span>{String(event.event_id ?? 'n/a')}</span>
                <span>{formatTimestamp(event.timestamp)}</span>
              </div>
            </div>
          ))
        )}
      </div>
      {timeline.next_cursor ? (
        <button className="office-view__load-more" onClick={onLoadMore} type="button">
          Load More
        </button>
      ) : null}
    </section>
  )
}

export function OfficeView() {
  const canvasRef = useRef(null)
  const animatorRef = useRef(null)
  const frameRef = useRef(0)
  const latestRef = useRef({
    view: null,
    connectionState: 'connecting',
    signalLost: false,
    lastUpdated: null,
  })

  const { view, connectionState, error, lastUpdated, signalLost, isOnline } = useProjectionView()
  const {
    entities,
    selectedEntityId,
    setSelectedEntityId,
    selectedEntity,
    selectedEntityType,
    entityTimeline,
    officeTimeline,
    integrityLatest,
    stabilityRuns,
    error: inspectionError,
    connectionState: inspectionConnectionState,
    loadMoreEntityTimeline,
    loadMoreOfficeTimeline,
  } = useInspectionData()

  if (animatorRef.current == null) {
    animatorRef.current = new OfficeAnimator(view)
  }

  useEffect(() => {
    animatorRef.current?.ingestView(view)
  }, [view])

  useEffect(() => {
    latestRef.current = {
      view,
      connectionState,
      signalLost,
      lastUpdated,
    }
  }, [view, connectionState, signalLost, lastUpdated])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) {
      return undefined
    }

    const renderer = createOfficeSceneRenderer(canvas)
    const renderLoop = (nowMs) => {
      const latest = latestRef.current
      const animationState = animatorRef.current?.tick(nowMs)
      renderer.render({
        animationState,
        view: latest.view,
        connectionState: latest.connectionState,
        signalLost: latest.signalLost,
        lastUpdated: latest.lastUpdated,
      })
      frameRef.current = window.requestAnimationFrame(renderLoop)
    }

    frameRef.current = window.requestAnimationFrame(renderLoop)
    const onResize = () => {
      renderer.resize()
    }
    window.addEventListener('resize', onResize)

    return () => {
      window.removeEventListener('resize', onResize)
      window.cancelAnimationFrame(frameRef.current)
      renderer.destroy()
    }
  }, [])

  const currentEventType =
    typeof view?.current_event?.type === 'string' && view.current_event.type.length > 0
      ? view.current_event.type
      : 'none'

  const schemaVersion = typeof view?.schema_version === 'number' ? String(view.schema_version) : 'n/a'
  const updatedAt = formatTimestamp(view?.last_updated_at ?? view?.timestamp ?? lastUpdated)
  const integritySummary = integrityLatest?.integrity_summary ?? {}
  const trustTrend = integrityLatest?.trust?.trend ?? {}
  const propagation = integrityLatest?.propagation ?? {}
  const latestRun = Array.isArray(stabilityRuns) && stabilityRuns.length > 0 ? stabilityRuns[0] : null

  return (
    <section className="office-view">
      <div className="panel office-view__meta">
        <div className="office-view__stats">
          <span>schema: {schemaVersion}</span>
          <span>queue: {queueValue(view)}</span>
          <span>current_event: {currentEventType}</span>
          <span>stream: {connectionState}</span>
          <span>online: {String(isOnline)}</span>
          <span>updated: {updatedAt}</span>
          <span>inspection_stream: {inspectionConnectionState}</span>
        </div>
        <div className="office-view__legend" aria-label="Office view legend">
          <span>
            <i className="office-view__dot office-view__dot--green" />
            Green = valid execution
          </span>
          <span>
            <i className="office-view__dot office-view__dot--red" />
            Red = policy denial
          </span>
          <span>
            <i className="office-view__dot office-view__dot--blue" />
            Blue = active processing
          </span>
        </div>
        <div className="office-view__error">stream_error: {error ?? 'n/a'}</div>
        <div className="office-view__error">inspection_error: {inspectionError ?? 'n/a'}</div>
      </div>

      <div className="office-view__canvas-shell">
        <canvas ref={canvasRef} className="office-view__canvas" aria-label="CCTV office projection visualization" />
      </div>

      <div className="office-view__inspection-grid">
        <section className="panel office-view__entity-list-panel">
          <header className="panel__header">
            <h2>Entities</h2>
          </header>
          <div className="office-view__entity-list">
            {entities.map((entity) => {
              const entityId = String(entity.id ?? '')
              const active = entityId === selectedEntityId
              return (
                <button
                  key={entityId}
                  className={active ? 'office-view__entity-button office-view__entity-button--active' : 'office-view__entity-button'}
                  onClick={() => setSelectedEntityId(entityId)}
                  type="button"
                >
                  <span>{entityId}</span>
                  <span>{String(entity.entity_type ?? 'agent')}</span>
                  <span>{String(entity.state ?? entity.role ?? '')}</span>
                </button>
              )
            })}
          </div>
        </section>

        <section className="panel office-view__entity-detail-panel">
          <header className="panel__header">
            <h2>Entity Detail</h2>
          </header>
          {selectedEntity ? (
            <div className="office-view__details">
              {renderEntityDetail('id', selectedEntity.id)}
              {renderEntityDetail('type', selectedEntityType)}
              {renderEntityDetail('role', selectedEntity.role)}
              {renderEntityDetail('state', selectedEntity.state)}
              {renderEntityDetail('present', selectedEntity.present)}
              {renderEntityDetail('age_seconds', selectedEntity.age_seconds)}
              {renderEntityDetail('busy_with', selectedEntity.busy_with)}
              {renderEntityDetail('last_event_type', selectedEntity.last_event_type)}
              {renderEntityDetail('last_event_at', formatTimestamp(selectedEntity.last_event_at))}
              {renderEntityDetail('restart_count', selectedEntity.restart_count)}
              {renderEntityDetail('missed_heartbeat_count', selectedEntity.missed_heartbeat_count)}
            </div>
          ) : (
            <p className="event-empty">Select an entity to inspect.</p>
          )}
        </section>

        <TimelineBlock title="Entity Timeline" timeline={entityTimeline} onLoadMore={loadMoreEntityTimeline} />
        <TimelineBlock title="Office Timeline" timeline={officeTimeline} onLoadMore={loadMoreOfficeTimeline} />

        <section className="panel office-view__integrity-panel">
          <header className="panel__header">
            <h2>Integrity Panel</h2>
          </header>
          <div className="office-view__details">
            {renderEntityDetail('latest_report', formatTimestamp(integrityLatest?.generated_at))}
            {renderEntityDetail('report_hash', integrityLatest?.report_hash ?? 'n/a')}
            {renderEntityDetail(
              'trust_rolling_slope',
              trustTrend?.rolling_slope ?? 'n/a',
            )}
            {renderEntityDetail(
              'trust_rolling_variance',
              trustTrend?.rolling_variance ?? 'n/a',
            )}
            {renderEntityDetail(
              'propagation_velocity',
              propagation?.knowledge_propagation_velocity ?? 'n/a',
            )}
            {renderEntityDetail(
              'arbitration_efficiency',
              integritySummary?.arbitration_efficiency_score ?? 'n/a',
            )}
            {renderEntityDetail('stability_run_status', latestRun?.status ?? 'n/a')}
            {renderEntityDetail('last_checkpoint_time', latestRun?.updated_at ?? 'n/a')}
          </div>
        </section>
      </div>
    </section>
  )
}
