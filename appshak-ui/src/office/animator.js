import { clamp, easeInOutCubic, lerp } from './effects.js'
import { projectOfficeModel } from './projection.js'

function positionOf(item) {
  return item ? { x: item.x, y: item.y } : null
}

export class OfficeAnimator {
  constructor({ reducedMotion = false } = {}) {
    this.reducedMotion = reducedMotion
    this.projection = projectOfficeModel(null)
    this.previousKey = null
    this.transition = null
    this.itemPosition = null
  }

  ingestOfficeModel(model, selectedTaskId = null) {
    const next = projectOfficeModel(model, selectedTaskId)
    if (next.semanticKey === this.previousKey) return

    const target = positionOf(next.workItem)
    const sameTask = Boolean(next.live && this.projection.live && next.taskId && next.taskId === this.projection.taskId)
    const from = sameTask ? (this.itemPosition ?? positionOf(this.projection.workItem) ?? target) : target
    const moved = from && target && (from.x !== target.x || from.y !== target.y)
    this.transition = !this.reducedMotion && sameTask && moved
      ? { from, target, startMs: null, durationMs: 900,
          fromZone: this.projection.zone, toZone: next.zone }
      : null
    this.itemPosition = from
    this.projection = next
    this.previousKey = next.semanticKey
  }

  tick(nowMs) {
    const now = Number.isFinite(nowMs) ? nowMs : 0
    let position = this.itemPosition
    let travel = null
    if (this.transition) {
      if (this.transition.startMs === null) this.transition.startMs = now
      const progress = clamp((now - this.transition.startMs) / this.transition.durationMs, 0, 1)
      const eased = easeInOutCubic(progress)
      position = {
        x: lerp(this.transition.from.x, this.transition.target.x, eased),
        y: lerp(this.transition.from.y, this.transition.target.y, eased),
      }
      this.itemPosition = position
      travel = { from: this.transition.from, target: this.transition.target, progress,
        fromZone: this.transition.fromZone, toZone: this.transition.toZone }
      if (progress >= 1) this.transition = null
    }

    return {
      avatars: Object.fromEntries(this.projection.workers.map((item) => [item.id, { x: item.x, y: item.y }])),
      workItemPosition: this.projection.live ? position : null,
      travel: this.projection.live ? travel : null,
      animating: Boolean(this.transition),
      pulses: [],
      lightLevel: this.projection.live ? 0.66 : 0.3,
      stressLevel: ['VALIDATION_FAILED', 'NEEDS_RECONCILIATION', 'HANDOFF_FAILED',
        'PROJECTION_ERROR', 'BACKEND_UNAVAILABLE'].includes(this.projection.state) ? 0.65 : 0,
      ambientPulse: 0,
      running: this.projection.state === 'ACTIVE / EXECUTING',
      queueSize: 0,
      currentEventType: null,
      officeProjection: this.projection,
    }
  }
}
