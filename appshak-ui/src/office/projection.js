import { OFFICE_ZONES } from './scene.js'

const WORKER_ZONE = {
  supervisor: 'supervisorDesk',
  command: 'commandDesk',
  recon: 'reconDesk',
  forge: 'forgeDesk',
}

const HANDOFF_STATES = new Set([
  'WAITING_FOR_CAPABILITY', 'HANDOFF_DISPATCHED',
  'EXTERNAL_PICKUP_ACKNOWLEDGED', 'EXTERNAL_RUNNING',
  'RESULT_RETURNED', 'HANDOFF_FAILED',
])

function clean(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function zoneForWorker(workerId) {
  return WORKER_ZONE[String(workerId ?? '').toLowerCase()] ?? 'boardroom'
}

function statusForTask(task) {
  if (!task) return 'UNKNOWN'
  const visual = task.visual_state
  const handoff = task.routing_state

  if (visual === 'NEEDS_RECONCILIATION' || handoff === 'UNKNOWN') return 'NEEDS_RECONCILIATION'
  if (['VALIDATION_FAILED', 'VALIDATION_ERROR', 'EXECUTION_FAILED'].includes(visual)) return visual
  if (visual === 'UNKNOWN_STATE') return 'UNKNOWN'

  if (task.handoff_role === 'SOURCE' && visual === 'COMPLETE') {
    if (handoff === 'WAITING_FOR_CAPABILITY') return handoff
    if (handoff === 'HANDOFF_DISPATCHED') return handoff
    if (handoff === 'EXTERNAL_PICKUP_ACKNOWLEDGED') return handoff
    if (handoff === 'RESULT_RETURNED') return handoff
    if (handoff === 'FAILED') return 'HANDOFF_FAILED'
  }
  if (task.handoff_role === 'DESTINATION') {
    if (visual === 'WORKING' && handoff === 'EXTERNAL_PICKUP_ACKNOWLEDGED' && task.attempt_state === 'RUNNING') {
      return 'EXTERNAL_RUNNING'
    }
    if (visual === 'ASSIGNED' && handoff === 'HANDOFF_DISPATCHED') return handoff
    if (visual === 'ASSIGNED' && handoff === 'EXTERNAL_PICKUP_ACKNOWLEDGED') return handoff
  }

  if (visual === 'WORKING') return 'ACTIVE / EXECUTING'
  if (visual === 'VALIDATING') return 'VALIDATION IN PROGRESS'
  if (visual === 'READY_FOR_VALIDATION') return 'VALIDATION_PENDING'
  if (visual === 'COMPLETE' && handoff === 'WAITING_FOR_CAPABILITY') return handoff
  if (visual === 'COMPLETE') return 'COMPLETE'
  if (['CREATED', 'ASSIGNED'].includes(visual)) return visual
  return 'UNKNOWN'
}

function zoneForState(state, workerId) {
  if (state === 'ACTIVE / EXECUTING') return zoneForWorker(workerId)
  if (state === 'VALIDATION_PENDING' || state === 'VALIDATION IN PROGRESS' || state === 'RESULT_RETURNED') return 'boardroom'
  if (['VALIDATION_FAILED', 'VALIDATION_ERROR', 'NEEDS_RECONCILIATION', 'EXECUTION_FAILED', 'HANDOFF_FAILED'].includes(state)) return 'reconDesk'
  if (HANDOFF_STATES.has(state)) return 'dispatchZone'
  if (state === 'COMPLETE') return 'forgeDesk'
  return 'boardroom'
}

function workItemPosition(state, zone) {
  if (state === 'WAITING_FOR_CAPABILITY') return { x: 0.265, y: 0.43 }
  if (state === 'HANDOFF_DISPATCHED') return { x: 0.365, y: 0.43 }
  if (state === 'EXTERNAL_PICKUP_ACKNOWLEDGED' || state === 'EXTERNAL_RUNNING') return { x: 0.42, y: 0.43 }
  if (state === 'ACTIVE / EXECUTING') {
    return { x: Math.min(0.93, zone.x + 0.075), y: Math.max(0.14, zone.y - 0.075) }
  }
  return { x: zone.x, y: zone.y }
}

function activeWorkers(tasks) {
  const byId = new Map()
  for (const task of tasks) {
    const id = clean(task.worker_id)
    if (!id || task.visual_state !== 'WORKING' || task.attempt_state !== 'RUNNING') continue
    if (task.handoff_role === 'DESTINATION' && task.routing_state === 'EXTERNAL_PICKUP_ACKNOWLEDGED') continue
    if (!byId.has(id)) byId.set(id, { id, taskId: task.task_id, zone: zoneForWorker(id) })
  }
  const workers = [...byId.values()].sort((a, b) => a.id.localeCompare(b.id))
  const zoneCounts = new Map()
  return workers.map((worker) => {
    const index = zoneCounts.get(worker.zone) ?? 0
    zoneCounts.set(worker.zone, index + 1)
    const base = OFFICE_ZONES[worker.zone]
    const column = index % 3
    const row = Math.floor(index / 3)
    return {
      ...worker,
      x: Math.max(0.08, Math.min(0.92, base.x + (column - 1) * 0.08)),
      y: Math.max(0.16, Math.min(0.87, base.y + row * 0.075 + 0.04)),
    }
  })
}

export function projectOfficeModel(model, selectedTaskId = null) {
  const input = model && typeof model === 'object' ? model : {}
  const freshness = clean(input.freshness) ?? 'UNKNOWN_STATE'
  const availability = clean(input.availability) ?? freshness
  const live = freshness === 'LIVE / CURRENT' && !input.error_state
  const tasks = Array.isArray(input.tasks) ? input.tasks : []
  const selected = live ? (tasks.find((task) => task.task_id === selectedTaskId) ?? tasks[0] ?? null) : null
  const state = live ? statusForTask(selected) : availability
  const zone = selected ? zoneForState(state, selected.worker_id) : 'securityCheckpoint'
  const workers = live ? activeWorkers(tasks) : []
  const worker = selected && state === 'ACTIVE / EXECUTING'
    ? workers.find((item) => item.id === selected.worker_id) ?? null
    : null
  const workItem = selected && live && OFFICE_ZONES[zone]
    ? { taskId: selected.task_id, zone, ...workItemPosition(state, OFFICE_ZONES[zone]) }
    : null

  return {
    state,
    freshness,
    availability,
    live,
    taskId: selected?.task_id ?? null,
    worker,
    workers,
    workItem,
    zone,
    artifactState: selected?.artifact_integrity ?? null,
    validationState: selected?.validation_state ?? null,
    handoffState: selected?.routing_state ?? null,
    handoffTarget: selected?.selected_target ?? null,
    pickupOwnerId: selected?.baton?.pickup_owner_id ?? null,
    handoffRole: selected?.handoff_role ?? null,
    taskCount: tasks.length,
    semanticKey: [
      state, freshness, selected?.task_id ?? '', zone, worker?.id ?? '',
      selected?.artifact_integrity ?? '', selected?.validation_state ?? '',
      selected?.routing_state ?? '', selected?.attempt_state ?? '',
      selected?.validation_id ?? '', selected?.baton?.dispatch_id ?? '',
      selected?.selected_target ?? '', selected?.baton?.pickup_owner_id ?? '',
      workers.map((item) => `${item.id}:${item.taskId}:${item.zone}`).join(','),
    ].join('|'),
  }
}
