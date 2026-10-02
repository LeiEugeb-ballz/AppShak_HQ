export const OFFICE_STALE_AFTER_MS = 6500

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function stringOrNull(value) {
  return typeof value === 'string' && value.trim().length > 0 ? value : null
}

function numberOrNull(value) {
  return Number.isFinite(value) ? value : null
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

function evidenceReason(evidence) {
  if (!isRecord(evidence)) return null
  return stringOrNull(evidence.reason) ?? stringOrNull(evidence.error)
}

function mapAttempt(row, current) {
  const outcome = isRecord(row.outcome) ? row.outcome : null
  return {
    attempt_id: stringOrNull(row.attempt_id),
    state: stringOrNull(row.state),
    authority_id: stringOrNull(row.authority_id),
    agent_id: stringOrNull(row.agent_id),
    workspace_id: stringOrNull(row.workspace_id),
    requested_operation: stringOrNull(row.requested_operation),
    validation_id: stringOrNull(row.validation_id),
    created_at: stringOrNull(row.created_at),
    started_at: stringOrNull(row.started_at),
    updated_at: stringOrNull(row.updated_at),
    outcome,
    outcome_reason: evidenceReason(outcome),
    return_code: numberOrNull(outcome?.return_code),
    current,
  }
}

function mapArtifact(row) {
  return {
    artifact_id: stringOrNull(row.artifact_id),
    attempt_id: stringOrNull(row.attempt_id),
    reference: stringOrNull(row.reference),
    sha256: stringOrNull(row.sha256),
    size_bytes: numberOrNull(row.size_bytes),
    kind: stringOrNull(row.kind),
    workspace_id: stringOrNull(row.workspace_id),
    producer_id: stringOrNull(row.producer_id),
    created_at: stringOrNull(row.created_at),
  }
}

function mapCheck(row) {
  return {
    criterion_id: stringOrNull(row.criterion_id),
    criterion_type: stringOrNull(row.criterion_type),
    status: stringOrNull(row.status),
    required: row.required === true,
    expected: isRecord(row.expected) ? row.expected : null,
    evidence: isRecord(row.evidence) ? row.evidence : null,
  }
}

function mapValidation(row, current) {
  const evidence = isRecord(row.evidence) ? row.evidence : null
  return {
    validation_id: stringOrNull(row.validation_id),
    source_request_id: stringOrNull(row.source_request_id),
    artifact_id: stringOrNull(row.artifact_id),
    validator_id: stringOrNull(row.validator_id),
    status: stringOrNull(row.status),
    related_attempt_id: stringOrNull(row.related_attempt_id),
    validated_sha256: stringOrNull(row.validated_sha256),
    validated_size_bytes: numberOrNull(row.validated_size_bytes),
    created_at: stringOrNull(row.created_at),
    started_at: stringOrNull(row.started_at),
    completed_at: stringOrNull(row.completed_at),
    updated_at: stringOrNull(row.updated_at),
    evidence,
    evidence_reason: evidenceReason(evidence),
    checks: requireRows(row.checks ?? [], 'validation check').map(mapCheck),
    current,
  }
}

function mapCriterion(row) {
  return {
    criterion_id: stringOrNull(row.criterion_id),
    criterion_type: stringOrNull(row.criterion_type),
    config: isRecord(row.config) ? row.config : null,
    required: row.required === true,
    source_ref: stringOrNull(row.source_ref),
    created_by: stringOrNull(row.created_by),
    created_at: stringOrNull(row.created_at),
  }
}

function mapBaton(row) {
  if (!row) return null
  return {
    baton_id: stringOrNull(row.baton_id),
    source_baton_id: stringOrNull(row.source_baton_id),
    status: stringOrNull(row.status),
    verification_status: stringOrNull(row.verification_status),
    verification_reason: stringOrNull(row.verification_reason),
    required_capability: stringOrNull(row.required_capability),
    work_package: stringOrNull(row.work_package),
    next_objective: stringOrNull(row.next_objective),
    completion_status: stringOrNull(row.completion_status),
    validation_id: stringOrNull(row.validation_id),
    producer_id: stringOrNull(row.producer_id),
    policy_version: stringOrNull(row.policy_version),
    git_commit: stringOrNull(row.git_commit),
    created_at: stringOrNull(row.created_at),
    updated_at: stringOrNull(row.updated_at),
    dispatch_id: stringOrNull(row.dispatch_id),
    dispatch_status: stringOrNull(row.dispatch_status),
    dispatch_reason: stringOrNull(row.dispatch_reason),
    dispatch_created_at: stringOrNull(row.dispatch_created_at),
    dispatch_updated_at: stringOrNull(row.dispatch_updated_at),
    target_id: stringOrNull(row.target_id),
  }
}

function taskGroup(taskState, visualState, routingState) {
  if (visualState === 'NEEDS_RECONCILIATION') return 'NEEDS_RECONCILIATION'
  if (routingState === 'WAITING_FOR_CAPABILITY') return 'WAITING_FOR_CAPABILITY'
  if (visualState === 'COMPLETE') return 'COMPLETE'
  if (visualState === 'VALIDATING') return 'VALIDATING'
  if (['EXECUTION_FAILED', 'VALIDATION_FAILED', 'VALIDATION_ERROR', 'FAILED'].includes(visualState)) return 'FAILED'
  if (['CREATED', 'ASSIGNED', 'READY_FOR_VALIDATION'].includes(taskState)) return 'WAITING'
  return 'ACTIVE'
}

function mapTask(row, batons) {
  const taskId = stringOrNull(row.task_id)
  const objective = stringOrNull(row.objective)
  const taskState = stringOrNull(row.state)
  if (!taskId || !objective || !taskState) {
    throw new Error('Canonical task is missing its ID, objective, or state')
  }

  const attemptRows = requireRows(row.attempts, 'attempt')
  const artifactRows = requireRows(row.artifacts, 'artifact')
  const validationRows = requireRows(row.validations, 'validation')
  const attempts = attemptRows.map((item, index) => mapAttempt(item, index === attemptRows.length - 1))
  const artifacts = artifactRows.map(mapArtifact)
  const validations = validationRows.map((item, index) => mapValidation(item, index === validationRows.length - 1))
  const criteria = requireRows(row.criteria ?? [], 'criterion').map(mapCriterion)
  const attempt = lastRow(attempts)
  const validation = lastRow(validations)
  const artifact = artifacts.find((item) => item.artifact_id === validation?.artifact_id)
    ?? lastRow(artifacts)
  const baton = mapBaton(batons.find((item) => item.task_id === taskId) ?? null)
  const validationState = validation?.status ?? null
  const artifactId = artifact?.artifact_id ?? null
  const artifactSha256 = artifact?.sha256 ?? null
  const validatedSha256 = validation?.validated_sha256 ?? null
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
  if (taskState === 'NEEDS_RECONCILIATION' || attempt?.state === 'NEEDS_RECONCILIATION' || validationState === 'NEEDS_RECONCILIATION') {
    visualState = 'NEEDS_RECONCILIATION'
  } else if (taskState === 'COMPLETE') {
    visualState = validationMatchesArtifact ? 'COMPLETE' : 'UNKNOWN_STATE'
  } else if (validationState === 'FAILED' || taskState === 'VALIDATION_FAILED') {
    visualState = 'VALIDATION_FAILED'
  } else if (validationState === 'ERROR' || taskState === 'VALIDATION_ERROR') {
    visualState = 'VALIDATION_ERROR'
  } else if (attempt?.state === 'FAILED' || taskState === 'EXECUTION_FAILED') {
    visualState = 'EXECUTION_FAILED'
  } else if (taskState === 'VALIDATING' || validationState === 'RUNNING') {
    visualState = 'VALIDATING'
  } else if (taskState === 'EXECUTING' && attempt?.state === 'RUNNING') {
    visualState = 'WORKING'
  }

  const routingState = baton?.dispatch_status ?? null
  return {
    task_id: taskId,
    source_request_id: stringOrNull(row.source_request_id),
    owner_id: stringOrNull(row.owner_id),
    objective,
    task_state: taskState,
    authority_id: stringOrNull(row.authority_id),
    assignment_authority_id: stringOrNull(row.assignment_authority_id),
    assignment_source: stringOrNull(row.assignment_source),
    assigned_at: stringOrNull(row.assigned_at),
    created_at: stringOrNull(row.created_at),
    updated_at: stringOrNull(row.updated_at),
    worker_id: stringOrNull(row.assigned_agent),
    workspace_id: stringOrNull(row.workspace_id),
    attempts,
    attempt_id: attempt?.attempt_id ?? null,
    attempt_state: attempt?.state ?? null,
    attempt_reason: attempt?.outcome_reason ?? null,
    artifacts,
    artifact_id: artifactId,
    artifact_reference: artifact?.reference ?? null,
    artifact_sha256: artifactSha256,
    artifact_size_bytes: artifact?.size_bytes ?? null,
    artifact_integrity: artifactIntegrity,
    criteria,
    validations,
    validation_id: validation?.validation_id ?? null,
    validation_state: validationState,
    validation_reason: validation?.evidence_reason ?? null,
    validated_sha256: validatedSha256,
    baton,
    baton_id: baton?.baton_id ?? null,
    baton_status: baton?.status ?? null,
    baton_verification_state: baton?.verification_status ?? null,
    required_capability: baton?.required_capability ?? null,
    routing_state: routingState,
    dispatch_id: baton?.dispatch_id ?? null,
    selected_target: baton?.target_id ?? null,
    visual_state: visualState,
    presentation_group: taskGroup(taskState, visualState, routingState),
    validation_matches_artifact: validationMatchesArtifact,
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

export function summarizeTasks(tasks) {
  const counts = {
    TOTAL: tasks.length,
    ACTIVE: 0,
    WAITING: 0,
    VALIDATING: 0,
    COMPLETE: 0,
    FAILED: 0,
    NEEDS_RECONCILIATION: 0,
    WAITING_FOR_CAPABILITY: 0,
  }
  for (const task of tasks) {
    if (task.presentation_group === 'ACTIVE') counts.ACTIVE += 1
    if (task.presentation_group === 'WAITING') counts.WAITING += 1
    if (task.visual_state === 'VALIDATING') counts.VALIDATING += 1
    if (task.visual_state === 'COMPLETE') counts.COMPLETE += 1
    if (['EXECUTION_FAILED', 'VALIDATION_FAILED', 'VALIDATION_ERROR', 'FAILED'].includes(task.visual_state)) counts.FAILED += 1
    if (task.visual_state === 'NEEDS_RECONCILIATION') counts.NEEDS_RECONCILIATION += 1
    if (task.routing_state === 'WAITING_FOR_CAPABILITY') counts.WAITING_FOR_CAPABILITY += 1
  }
  return counts
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
    task_counts: summarizeTasks(tasks),
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
