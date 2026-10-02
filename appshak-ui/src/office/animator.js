import { clamp, easeInOutCubic, lerp } from './effects.js'
import { projectOfficeModel } from './projection.js'

function positionFor(projection) {
  if (!projection?.worker) return null
  return { x: projection.worker.x, y: projection.worker.y }
}

export class OfficeAnimator {
  constructor() {
    this.lastTickMs = null
    this.projection = projectOfficeModel(null)
    this.previousKey = null
    this.transition = null
    this.position = null
  }

  ingestOfficeModel(model, selectedTaskId = null) {
    const next = projectOfficeModel(model, selectedTaskId)
    if (next.semanticKey === this.previousKey) return
    const target = positionFor(next)
    const sameWorker = this.projection.worker?.id === next.worker?.id
    const from = sameWorker ? (this.position ?? target) : target
    this.transition = sameWorker && from && target && (from.x !== target.x || from.y !== target.y)
      ? { from, target, startMs: null, durationMs: 700 }
      : null
    this.position = target
    this.projection = next
    this.previousKey = next.semanticKey
  }

  tick(nowMs) {
    const now = Number.isFinite(nowMs) ? nowMs : 0
    if (this.lastTickMs === null) this.lastTickMs = now
    this.lastTickMs = now
    let position = this.position
    if (this.transition) {
      if (this.transition.startMs === null) this.transition.startMs = now
      const progress = clamp((now - this.transition.startMs) / this.transition.durationMs, 0, 1)
      const eased = easeInOutCubic(progress)
      position = {
        x: lerp(this.transition.from.x, this.transition.target.x, eased),
        y: lerp(this.transition.from.y, this.transition.target.y, eased),
      }
      this.position = position
      if (progress >= 1) this.transition = null
    }
    return {
      avatars: position && this.projection.worker ? { [this.projection.worker.id]: position } : {},
      pulses: [],
      lightLevel: this.projection.live ? 0.62 : 0.28,
      stressLevel: ['VALIDATION_FAILED', 'NEEDS_RECONCILIATION', 'PROJECTION_ERROR', 'BACKEND_UNAVAILABLE'].includes(this.projection.state) ? 0.72 : 0,
      ambientPulse: 0,
      running: this.projection.state === 'ACTIVE / EXECUTING',
      queueSize: 0,
      currentEventType: null,
      officeProjection: this.projection,
    }
  }
}
