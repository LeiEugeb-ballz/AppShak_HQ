import {
  clamp,
  damp,
  easeInOutCubic,
  lerp,
  pulseEnvelope,
  queueToStress,
} from './effects'
import { OFFICE_ZONES } from './scene'

const AVATAR_IDS = ['supervisor', 'recon', 'forge', 'command']

const HOME_ZONE_BY_AVATAR = {
  supervisor: 'supervisorIdle',
  recon: 'reconDesk',
  forge: 'forgeDesk',
  command: 'commandDesk',
}

const DESK_ZONE_BY_ORIGIN = {
  supervisor: 'supervisorDesk',
  recon: 'reconDesk',
  forge: 'forgeDesk',
  command: 'commandDesk',
}

function isRecord(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function readCount(value, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function normalizeIncomingView(raw) {
  const input = isRecord(raw) ? raw : {}
  const currentEvent = isRecord(input.current_event) ? input.current_event : {}
  const toolAudit = isRecord(input.tool_audit_counts) ? input.tool_audit_counts : {}

  const eventType =
    typeof currentEvent.type === 'string' && currentEvent.type.trim().length > 0
      ? currentEvent.type.trim()
      : null

  const eventOrigin =
    typeof currentEvent.origin_id === 'string' && currentEvent.origin_id.trim().length > 0
      ? currentEvent.origin_id.trim().toLowerCase()
      : null

  return {
    running: Boolean(input.running),
    eventQueueSize: Math.max(0, readCount(input.event_queue_size, 0)),
    currentEventType: eventType,
    currentEventOrigin: eventOrigin,
    toolAllowed: Math.max(0, readCount(toolAudit.allowed, 0)),
    toolDenied: Math.max(0, readCount(toolAudit.denied, 0)),
  }
}

function zonePoint(zoneName) {
  const zone = OFFICE_ZONES[zoneName]
  if (!zone) {
    return { x: 0.5, y: 0.5 }
  }
  return { x: zone.x, y: zone.y }
}

export class OfficeAnimator {
  constructor(initialView) {
    this.queue = []
    this.activeAction = null
    this.lastTickMs = null
    this.pulses = []

    this.state = {
      clock: 0,
      lightLevel: 0.45,
      targetLight: 0.45,
      stressLevel: 0,
      targetStress: 0,
      ambientPulse: 0,
    }

    this.avatarPhases = {
      supervisor: 0.2,
      recon: 1.9,
      forge: 3.4,
      command: 5.1,
    }

    this.avatars = {}
    for (const avatarId of AVATAR_IDS) {
      const home = zonePoint(HOME_ZONE_BY_AVATAR[avatarId])
      this.avatars[avatarId] = {
        x: home.x,
        y: home.y,
      }
    }

    this.prevView = null
    if (initialView) {
      this.resetToView(initialView)
    }
  }

  resetToView(rawView) {
    const next = normalizeIncomingView(rawView)
    this.prevView = next
    this.queue = []
    this.activeAction = null
    this.pulses = []
    this.state.targetStress = queueToStress(next.eventQueueSize)
    this.state.stressLevel = this.state.targetStress
    this.state.targetLight = next.running ? 0.78 : 0.36
    this.state.lightLevel = this.state.targetLight
    this.state.ambientPulse = 0
    const supervisorTarget = zonePoint(next.running ? 'supervisorDesk' : 'supervisorIdle')
    this.avatars.supervisor.x = supervisorTarget.x
    this.avatars.supervisor.y = supervisorTarget.y
  }

  ingestView(rawView) {
    const next = normalizeIncomingView(rawView)
    const previous = this.prevView

    if (previous === null) {
      this.prevView = next
      this.state.targetStress = queueToStress(next.eventQueueSize)
      this.state.stressLevel = this.state.targetStress
      this.state.targetLight = next.running ? 0.78 : 0.36
      this.state.lightLevel = this.state.targetLight
      const supervisorTarget = zonePoint(next.running ? 'supervisorDesk' : 'supervisorIdle')
      this.avatars.supervisor.x = supervisorTarget.x
      this.avatars.supervisor.y = supervisorTarget.y
      return
    }

    if (!previous.running && next.running) {
      this.enqueue({
        kind: 'move',
        avatarId: 'supervisor',
        zone: 'supervisorDesk',
        durationMs: 1700,
      })
      this.enqueue({
        kind: 'light',
        to: 0.82,
        durationMs: 1100,
      })
    }

    if (previous.running && !next.running) {
      this.enqueue({
        kind: 'move',
        avatarId: 'supervisor',
        zone: 'supervisorIdle',
        durationMs: 1200,
      })
      this.enqueue({
        kind: 'light',
        to: 0.35,
        durationMs: 1100,
      })
    }

    if (previous.eventQueueSize !== next.eventQueueSize) {
      this.state.targetStress = queueToStress(next.eventQueueSize)
    }

    if (next.currentEventType && next.currentEventType !== previous.currentEventType) {
      this.enqueueEventReaction(next.currentEventType, next.currentEventOrigin)
    }

    if (next.toolAllowed > previous.toolAllowed) {
      this.enqueue({
        kind: 'securityBlink',
        color: '#39d98a',
        durationMs: 900,
      })
    }

    if (next.toolDenied > previous.toolDenied) {
      this.enqueue({
        kind: 'securityBlink',
        color: '#e85d68',
        durationMs: 900,
      })
    }

    this.prevView = next
  }

  enqueueEventReaction(eventTypeRaw, eventOriginRaw) {
    const eventType = String(eventTypeRaw).trim().toUpperCase()
    if (!eventType) {
      return
    }

    if (eventType.includes('HEARTBEAT')) {
      this.state.ambientPulse = Math.max(this.state.ambientPulse, 0.45)
      return
    }

    if (eventType === 'SUPERVISOR_START') {
      this.enqueue({
        kind: 'zonePulse',
        zone: 'supervisorDesk',
        color: '#4f95ff',
        durationMs: 1200,
      })
      return
    }

    if (eventType === 'SUPERVISOR_STOP') {
      this.enqueue({
        kind: 'zonePulse',
        zone: 'supervisorDesk',
        color: '#6f87b8',
        durationMs: 1100,
      })
      this.enqueue({
        kind: 'light',
        to: 0.32,
        durationMs: 900,
      })
      return
    }

    if (eventType === 'PROPOSAL_INVALID') {
      this.enqueue({
        kind: 'zonePulse',
        zone: 'boardroom',
        color: '#ea5f6d',
        durationMs: 1300,
      })
      return
    }

    if (eventType === 'INTENT_DISPATCH') {
      this.enqueue({
        kind: 'zonePulse',
        zone: 'dispatchZone',
        color: '#4ad08c',
        durationMs: 1200,
      })
      return
    }

    if (eventType === 'WORKER_RESTARTED') {
      const eventOrigin =
        typeof eventOriginRaw === 'string' && eventOriginRaw.length > 0
          ? eventOriginRaw.toLowerCase()
          : ''
      const zone = DESK_ZONE_BY_ORIGIN[eventOrigin] ?? 'commandDesk'
      this.enqueue({
        kind: 'deskFlicker',
        zone,
        durationMs: 900,
      })
    }
  }

  enqueue(action) {
    if (!action || !action.kind) {
      return
    }

    if (action.kind === 'light') {
      this.queue = this.queue.filter((item) => item.kind !== 'light')
      this.queue.push(action)
      return
    }

    if (action.kind === 'move') {
      const currentMove = this.activeAction
      if (
        currentMove &&
        currentMove.kind === 'move' &&
        currentMove.avatarId === action.avatarId &&
        currentMove.zone === action.zone
      ) {
        return
      }
      this.queue = this.queue.filter(
        (item) => !(item.kind === 'move' && item.avatarId === action.avatarId),
      )
      this.queue.push(action)
      return
    }

    if (action.kind === 'securityBlink') {
      this.queue = this.queue.filter((item) => item.kind !== 'securityBlink')
      this.queue.push(action)
      return
    }

    if (action.kind === 'zonePulse') {
      const alreadyQueued = this.queue.some(
        (item) =>
          item.kind === 'zonePulse' && item.zone === action.zone && item.color === action.color,
      )
      if (alreadyQueued) {
        return
      }
      this.queue.push(action)
      return
    }

    if (action.kind === 'deskFlicker') {
      this.queue = this.queue.filter(
        (item) => !(item.kind === 'deskFlicker' && item.zone === action.zone),
      )
      this.queue.push(action)
      return
    }

    this.queue.push(action)
  }

  tick(nowMs) {
    if (!Number.isFinite(nowMs)) {
      return this.buildFrameState(0)
    }

    if (this.lastTickMs === null) {
      this.lastTickMs = nowMs
    }
    const deltaSeconds = clamp((nowMs - this.lastTickMs) / 1000, 0, 0.08)
    this.lastTickMs = nowMs
    this.state.clock += deltaSeconds

    this.state.lightLevel = damp(this.state.lightLevel, this.state.targetLight, deltaSeconds, 3.1)
    this.state.stressLevel = damp(this.state.stressLevel, this.state.targetStress, deltaSeconds, 2.3)
    this.state.ambientPulse = damp(this.state.ambientPulse, 0, deltaSeconds, 4.3)

    this.pulses = this.pulses.filter((pulse) => nowMs < pulse.startMs + pulse.durationMs)

    if (!this.activeAction && this.queue.length > 0) {
      this.startAction(this.queue.shift(), nowMs)
    }

    if (this.activeAction) {
      this.updateAction(nowMs)
    }

    return this.buildFrameState(nowMs)
  }

  startAction(action, nowMs) {
    if (!action) {
      return
    }

    if (action.kind === 'move') {
      const avatar = this.avatars[action.avatarId]
      if (!avatar) {
        return
      }
      const target = zonePoint(action.zone)
      this.activeAction = {
        kind: 'move',
        avatarId: action.avatarId,
        zone: action.zone,
        startMs: nowMs,
        durationMs: Math.max(800, readCount(action.durationMs, 1200)),
        fromX: avatar.x,
        fromY: avatar.y,
        toX: target.x,
        toY: target.y,
      }
      return
    }

    if (action.kind === 'light') {
      this.activeAction = {
        kind: 'light',
        startMs: nowMs,
        durationMs: Math.max(800, readCount(action.durationMs, 1000)),
        from: this.state.targetLight,
        to: clamp(readCount(action.to, this.state.targetLight), 0.2, 0.9),
      }
      return
    }

    if (action.kind === 'zonePulse') {
      this.pushPulse(
        action.zone,
        action.color ?? '#68a8ff',
        Math.max(800, readCount(action.durationMs, 1000)),
        nowMs,
      )
      this.activeAction = {
        kind: 'hold',
        startMs: nowMs,
        durationMs: 800,
      }
      return
    }

    if (action.kind === 'securityBlink') {
      this.pushPulse(
        'securityCheckpoint',
        action.color ?? '#52cc84',
        Math.max(800, readCount(action.durationMs, 900)),
        nowMs,
      )
      this.activeAction = {
        kind: 'hold',
        startMs: nowMs,
        durationMs: 800,
      }
      return
    }

    if (action.kind === 'deskFlicker') {
      this.pushPulse(action.zone, '#8eb6ee', Math.max(800, readCount(action.durationMs, 850)), nowMs)
      this.state.ambientPulse = Math.max(this.state.ambientPulse, 0.3)
      this.activeAction = {
        kind: 'hold',
        startMs: nowMs,
        durationMs: 800,
      }
    }
  }

  updateAction(nowMs) {
    const action = this.activeAction
    if (!action) {
      return
    }
    const progress = clamp((nowMs - action.startMs) / action.durationMs, 0, 1)
    const eased = easeInOutCubic(progress)

    if (action.kind === 'move') {
      const avatar = this.avatars[action.avatarId]
      if (avatar) {
        avatar.x = lerp(action.fromX, action.toX, eased)
        avatar.y = lerp(action.fromY, action.toY, eased)
      }
    } else if (action.kind === 'light') {
      this.state.targetLight = lerp(action.from, action.to, eased)
    }

    if (progress >= 1) {
      if (action.kind === 'move') {
        const avatar = this.avatars[action.avatarId]
        if (avatar) {
          avatar.x = action.toX
          avatar.y = action.toY
        }
      } else if (action.kind === 'light') {
        this.state.targetLight = action.to
      }
      this.activeAction = null
    }
  }

  pushPulse(zone, color, durationMs, startMs) {
    this.pulses.push({
      zone,
      color,
      startMs,
      durationMs: Math.max(400, durationMs),
    })
  }

  buildFrameState(nowMs) {
    const pulses = []
    for (const pulse of this.pulses) {
      const progress = clamp((nowMs - pulse.startMs) / pulse.durationMs, 0, 1)
      const intensity = pulseEnvelope(progress)
      if (intensity > 0.01) {
        pulses.push({
          zone: pulse.zone,
          color: pulse.color,
          intensity,
        })
      }
    }

    const avatars = {}
    for (const avatarId of AVATAR_IDS) {
      const base = this.avatars[avatarId]
      if (!base) {
        continue
      }
      const phase = this.avatarPhases[avatarId] ?? 0
      const driftX = Math.sin(this.state.clock * 0.75 + phase) * 0.0025
      const driftY = Math.cos(this.state.clock * 0.95 + phase) * 0.0018
      avatars[avatarId] = {
        x: clamp(base.x + driftX, 0.02, 0.98),
        y: clamp(base.y + driftY, 0.02, 0.98),
      }
    }

    return {
      avatars,
      pulses,
      lightLevel: this.state.lightLevel,
      stressLevel: this.state.stressLevel,
      ambientPulse: this.state.ambientPulse,
      running: this.prevView ? this.prevView.running : false,
      queueSize: this.prevView ? this.prevView.eventQueueSize : 0,
      currentEventType: this.prevView ? this.prevView.currentEventType : null,
    }
  }
}
