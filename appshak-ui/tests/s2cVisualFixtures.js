import { buildOfficeViewModel, mapCanonicalOfficeState, OFFICE_STALE_AFTER_MS } from '../src/office/officeState.js'

export const VISUAL_SCENARIOS = [
  'active',
  'validation_failed',
  'needs_reconciliation',
  'complete',
  'waiting_for_capability',
  'stale_unavailable',
]

function task(id, state, attemptState, validationState = null, baton = false) {
  const artifact = attemptState === 'SUCCEEDED'
    ? [{ artifact_id: `artifact-${id}`, attempt_id: `attempt-${id}`, reference: 'output.txt', sha256: `sha-${id}`, size_bytes: 10 }]
    : []
  return {
    task_id: id,
    objective: `S2C visual fixture: ${id}`,
    state,
    assigned_agent: 'command',
    workspace_id: 'fixture-workspace',
    attempts: [{ attempt_id: `attempt-${id}`, state: attemptState }],
    artifacts: artifact,
    criteria: [{ criterion_id: `criterion-${id}`, criterion_type: 'FILE_EXISTS', required: true }],
    validations: validationState ? [{
      validation_id: `validation-${id}`,
      status: validationState,
      artifact_id: `artifact-${id}`,
      validated_sha256: validationState === 'PASSED' ? `sha-${id}` : null,
      evidence: validationState === 'FAILED' ? { reason: 'fixture validation failed' } : { integrity_match: true },
      checks: [],
    }] : [],
    fixture_baton: baton,
  }
}

const SCENARIOS = {
  active: task('active', 'EXECUTING', 'RUNNING'),
  validation_failed: task('validation-failed', 'VALIDATION_FAILED', 'SUCCEEDED', 'FAILED'),
  needs_reconciliation: task('needs-reconciliation', 'NEEDS_RECONCILIATION', 'NEEDS_RECONCILIATION'),
  complete: task('complete', 'COMPLETE', 'SUCCEEDED', 'PASSED'),
  waiting_for_capability: task('waiting', 'COMPLETE', 'SUCCEEDED', 'PASSED', true),
  stale_unavailable: task('stale', 'COMPLETE', 'SUCCEEDED', 'PASSED', true),
}

export function createVisualScenario(name) {
  if (!Object.hasOwn(SCENARIOS, name)) throw new Error(`Unknown visual scenario: ${name}`)
  const row = SCENARIOS[name]
  const taskRow = { ...row }
  delete taskRow.fixture_baton
  const raw = {
    source: 'canonical_sqlite',
    tasks: [taskRow],
    batons: row.fixture_baton ? [{
      baton_id: 'BATON-fixture',
      task_id: row.task_id,
      status: 'VERIFIED',
      verification_status: 'VERIFIED',
      dispatch_status: 'WAITING_FOR_CAPABILITY',
      target_id: null,
    }] : [],
  }
  const receivedAt = 10_000
  const unavailable = name === 'stale_unavailable'
  const model = buildOfficeViewModel(mapCanonicalOfficeState(raw), {
    receivedAt,
    now: receivedAt + (unavailable ? OFFICE_STALE_AFTER_MS + 1 : 1),
    errorKind: unavailable ? 'BACKEND_UNAVAILABLE' : null,
    errorMessage: unavailable ? 'Fixture: backend unavailable' : null,
  })
  return { name, raw, model }
}
