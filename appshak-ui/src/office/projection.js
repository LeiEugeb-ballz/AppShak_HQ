import { OFFICE_ZONES } from './scene.js'

const WORKER_ZONE = {
  supervisor: 'supervisorDesk',
  command: 'commandDesk',
  recon: 'reconDesk',
  forge: 'forgeDesk',
}

function clean(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function zoneForWorker(workerId) {
  return WORKER_ZONE[String(workerId ?? '').toLowerCase()] ?? 'boardroom'
}

function statusForTask(task) {
  if (!task) return 'UNKNOWN'
  if (task.visual_state === 'WORKING') return 'ACTIVE / EXECUTING'
  if (task.visual_state === 'VALIDATING') return 'VALIDATION IN PROGRESS'
  if (task.visual_state === 'VALIDATION_FAILED') return 'VALIDATION_FAILED'
  if (task.visual_state === 'NEEDS_RECONCILIATION') return 'NEEDS_RECONCILIATION'
  if (task.visual_state === 'COMPLETE' && task.routing_state === 'WAITING_FOR_CAPABILITY') return 'WAITING_FOR_CAPABILITY'
  if (task.visual_state === 'COMPLETE') return 'COMPLETE'
  if (task.visual_state === 'UNKNOWN_STATE') return 'UNKNOWN'
  if (['EXECUTION_FAILED', 'VALIDATION_ERROR', 'READY_FOR_VALIDATION', 'ASSIGNED', 'CREATED'].includes(task.visual_state)) {
    return task.visual_state
  }
  return 'UNKNOWN'
}

export function projectOfficeModel(model, selectedTaskId = null) {
  const input = model && typeof model === 'object' ? model : {}
  const freshness = clean(input.freshness) ?? 'UNKNOWN_STATE'
  const availability = clean(input.availability) ?? freshness
  const live = freshness === 'LIVE / CURRENT' && !input.error_state
  const tasks = Array.isArray(input.tasks) ? input.tasks : []
  // Match the console's selected task; both surfaces default to the first ATS row.
  const selected = live ? (tasks.find((task) => task.task_id === selectedTaskId) ?? tasks[0] ?? null) : null
  const state = live ? statusForTask(selected) : availability
  // The assigned executor is not the independent validator.
  const workerId = selected && state === 'ACTIVE / EXECUTING'
    ? clean(selected.worker_id) : null
  let zone = selected ? 'boardroom' : 'securityCheckpoint'
  if (state === 'ACTIVE / EXECUTING') zone = zoneForWorker(workerId)
  if (state === 'VALIDATION IN PROGRESS') zone = 'boardroom'
  if (state === 'VALIDATION_FAILED') zone = 'reconDesk'
  if (state === 'NEEDS_RECONCILIATION') zone = 'reconDesk'
  if (state === 'WAITING_FOR_CAPABILITY') zone = 'dispatchZone'
  if (state === 'COMPLETE') zone = 'forgeDesk'

  const worker = workerId && OFFICE_ZONES[zone]
    ? { id: workerId, zone, taskId: selected.task_id, x: OFFICE_ZONES[zone].x, y: OFFICE_ZONES[zone].y }
    : null
  return {
    state,
    freshness,
    availability,
    live,
    taskId: selected?.task_id ?? null,
    worker,
    zone,
    artifactState: selected?.artifact_integrity ?? null,
    validationState: selected?.validation_state ?? null,
    handoffState: selected?.routing_state ?? null,
    taskCount: tasks.length,
    semanticKey: [
      state, freshness, selected?.task_id ?? '', workerId ?? '',
      selected?.artifact_integrity ?? '', selected?.validation_state ?? '',
      selected?.routing_state ?? '', selected?.validation_id ?? '',
    ].join('|'),
  }
}
