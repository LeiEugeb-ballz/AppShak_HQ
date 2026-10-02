export const OFFICE_STALE_AFTER_MS = 6500

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function stringOrNull(value) {
  return typeof value === 'string' && value.trim().length > 0 ? value : null
}

function lastRow(value) {
  return Array.isArray(value) && value.length > 0 ? value[value.length - 1] : null
}

function requireRows(value, label) {
  if (!Array.isArray(value) || value.some((row) => !isRecord(row))) {
    throw new Error(`Invalid canonical ${label} rows`)
  }
  return value
}

function mapTask(row, batons) {
  const taskId = stringOrNull(row.task_id)
  const objective = stringOrNull(row.objective)
  const taskState = stringOrNull(row.state)
  if (!taskId || !objective || !taskState) {
    throw new Error('Canonical task is missing its ID, objective, or state')
  }

  const attempt = lastRow(requireRows(row.attempts, 'attempt'))
  const artifacts = requireRows(row.artifacts, 'artifact')
  const validation = lastRow(requireRows(row.validations, 'validation'))
  const artifact = artifacts.find((item) => item.artifact_id === validation?.artifact_id)
    ?? lastRow(artifacts)
  const baton = batons.find((item) => item.task_id === taskId) ?? null
  const validationState = stringOrNull(validation?.status)
  const artifactId = stringOrNull(artifact?.artifact_id)
  const artifactSha256 = stringOrNull(artifact?.sha256)
  const validatedSha256 = stringOrNull(validation?.validated_sha256)
  const validationMatchesArtifact = Boolean(
    validationState === 'PASSED' && artifactId && artifactSha256 && validatedSha256 &&
    validation?.artifact_id === artifactId && validatedSha256 === artifactSha256,
  )

  let artifactIntegrity = null
  if (artifact) {
    artifactIntegrity = validationState === 'PASSED'
      ? (validationMatchesArtifact ? 'MATCHES_PERSISTED_VALIDATION' : 'INCONSISTENT')
      : 'RECORDED_UNVALIDATED'
  }

  let visualState = taskState
  if (taskState === 'NEEDS_RECONCILIATION' || attempt?.state === 'NEEDS_RECONCILIATION') {
    visualState = 'NEEDS_RECONCILIATION'
  } else if (taskState === 'COMPLETE') {
    visualState = validationMatchesArtifact ? 'COMPLETE' : 'UNKNOWN_STATE'
  } else if (validationState === 'FAILED') {
    visualState = 'VALIDATION_FAILED'
  } else if (taskState === 'VALIDATING' || validationState === 'RUNNING') {
    visualState = 'VALIDATING'
  } else if (taskState === 'EXECUTING' && attempt?.state === 'RUNNING') {
    visualState = 'WORKING'
  }

  return {
    task_id: taskId,
    objective,
    task_state: taskState,
    worker_id: stringOrNull(row.assigned_agent),
    workspace_id: stringOrNull(row.workspace_id),
    attempt_id: stringOrNull(attempt?.attempt_id),
    attempt_state: stringOrNull(attempt?.state),
    artifact_id: artifactId,
    artifact_reference: stringOrNull(artifact?.reference),
    artifact_sha256: artifactSha256,
    artifact_size_bytes: Number.isFinite(artifact?.size_bytes) ? artifact.size_bytes : null,
    artifact_integrity: artifactIntegrity,
    validation_id: stringOrNull(validation?.validation_id),
    validation_state: validationState,
    validated_sha256: validatedSha256,
    baton_id: stringOrNull(baton?.baton_id),
    baton_status: stringOrNull(baton?.status),
    baton_verification_state: stringOrNull(baton?.verification_status),
    required_capability: stringOrNull(baton?.required_capability),
    routing_state: stringOrNull(baton?.dispatch_status),
    dispatch_id: stringOrNull(baton?.dispatch_id),
    selected_target: stringOrNull(baton?.target_id),
    visual_state: visualState,
  }
}

export function mapCanonicalOfficeState(payload) {
  if (!isRecord(payload) || payload.source !== 'canonical_sqlite') {
    throw new Error('Office response is not canonical SQLite state')
  }
  const tasks = requireRows(payload.tasks, 'task')
  const batons = requireRows(payload.batons, 'baton')
  return {
    source: payload.source,
    tasks: tasks.map((row) => mapTask(row, batons)),
  }
}

export function buildOfficeViewModel(
  canonicalState,
  { receivedAt = null, now = Date.now(), errorKind = null, errorMessage = null } = {},
) {
  const hasState = isRecord(canonicalState) && canonicalState.source === 'canonical_sqlite'
  const ageMs = Number.isFinite(receivedAt) ? Math.max(0, now - receivedAt) : null
  const freshness = !hasState ? 'UNKNOWN_STATE'
    : errorKind || ageMs === null || ageMs > OFFICE_STALE_AFTER_MS ? 'STALE'
      : 'LIVE / CURRENT'
  const tasks = hasState ? canonicalState.tasks : []
  const primaryTask = tasks[0] ?? null
  const availability = errorKind ?? freshness

  return {
    source: hasState ? canonicalState.source : null,
    tasks,
    primary_task_id: primaryTask?.task_id ?? null,
    freshness,
    availability,
    error_state: errorKind,
    error_message: errorMessage,
    received_at: Number.isFinite(receivedAt) ? new Date(receivedAt).toISOString() : null,
    age_ms: ageMs,
    scene_status: freshness === 'LIVE / CURRENT'
      ? (primaryTask?.routing_state === 'WAITING_FOR_CAPABILITY' && primaryTask.visual_state === 'COMPLETE'
        ? 'COMPLETE / WAITING_FOR_CAPABILITY'
        : primaryTask?.visual_state ?? 'NO TASKS')
      : availability,
  }
}
