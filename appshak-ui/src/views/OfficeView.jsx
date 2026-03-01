import { useEffect, useRef } from 'react'
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

  const {
    view,
    connectionState,
    error,
    lastUpdated,
    signalLost,
    isOnline,
  } = useProjectionView()

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
    const onVisibilityChange = () => {
      if (document.visibilityState !== 'visible') {
        return
      }
      animatorRef.current?.resetToView(latestRef.current.view)
    }
    window.addEventListener('resize', onResize)
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      window.removeEventListener('resize', onResize)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.cancelAnimationFrame(frameRef.current)
      renderer.destroy()
    }
  }, [])

  const currentEventType =
    typeof view?.current_event?.type === 'string' && view.current_event.type.length > 0
      ? view.current_event.type
      : 'none'

  const schemaVersion =
    typeof view?.schema_version === 'number' ? String(view.schema_version) : 'n/a'

  const updatedAt = formatTimestamp(view?.last_updated_at ?? view?.timestamp ?? lastUpdated)

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
      </div>

      <div className="office-view__canvas-shell">
        <canvas
          ref={canvasRef}
          className="office-view__canvas"
          aria-label="CCTV office projection visualization"
        />
      </div>
    </section>
  )
}
