import React from 'react'
import { createRoot } from 'react-dom/client'
import '../src/index.css'
import '../src/App.css'
import { OfficeWorkflowPanel } from '../src/components/OfficeWorkflowPanel'
import { buildOfficeViewModel, mapCanonicalOfficeState, OFFICE_STALE_AFTER_MS } from '../src/office/officeState'

// Isolated engineering fixtures. Production App.jsx never imports this file.
function task(id, objective, state, attemptState, validationState = null, waiting = false) {
  const hasArtifact = ['SUCCEEDED'].includes(attemptState)
  return {
    task_id: id,
    source_request_id: `source-${id}`,
    owner_id: 'operator-owner',
    objective,
    authority_id: `authority-${id}`,
    state,
    assigned_agent: 'command',
    workspace_id: `worktree:command:E:\\AppShak_HQ\\workspaces\\${id}`,
    assignment_authority_id: `authority-${id}`,
    assignment_source: `assignment-${id}`,
    assigned_at: '2026-10-02T10:01:00Z',
    created_at: '2026-10-02T10:00:00Z',
    updated_at: '2026-10-02T10:05:00Z',
    attempts: [{ attempt_id: `attempt-${id}`, state: attemptState, agent_id: 'command',
      requested_operation: 'write controlled artifact', created_at: '2026-10-02T10:02:00Z',
      started_at: '2026-10-02T10:02:01Z', updated_at: '2026-10-02T10:03:00Z',
      outcome: attemptState === 'FAILED' ? { reason: 'command returned non-zero', return_code: 2 } : null }],
    artifacts: hasArtifact ? [{ artifact_id: `artifact-${id}`, attempt_id: `attempt-${id}`,
      reference: `E:\\AppShak_HQ\\workspaces\\${id}\\output.txt`, size_bytes: 128,
      sha256: `sha256-${id}`, kind: 'FILE', producer_id: 'command', created_at: '2026-10-02T10:03:00Z' }] : [],
    criteria: [{ criterion_id: `criterion-${id}`, criterion_type: 'FILE_EXISTS', config: {},
      required: true, source_ref: `owner-criterion-${id}`, created_by: 'operator-owner' }],
    validations: validationState ? [{ validation_id: `validation-${id}`, status: validationState,
      artifact_id: `artifact-${id}`, validator_id: 'system:deterministic-file-validator',
      related_attempt_id: `validator-attempt-${id}`,
      validated_sha256: validationState === 'PASSED' ? `sha256-${id}` : null,
      completed_at: '2026-10-02T10:04:00Z',
      evidence: validationState === 'FAILED' ? { reason: 'expected digest did not match' } : { integrity_match: true },
      checks: [{ criterion_id: `criterion-${id}`, criterion_type: 'FILE_EXISTS',
        status: validationState, required: true, expected: {}, evidence: { observed: { exists: true } } }] }] : [],
    fixture_waiting: waiting,
  }
}

const tasks = [
  task('active', 'Generate the current controlled artifact', 'EXECUTING', 'RUNNING'),
  task('validation-failed', 'Inspect a produced artifact that failed validation', 'VALIDATION_FAILED', 'SUCCEEDED', 'FAILED'),
  task('needs-reconciliation', 'Resolve an uncertain execution outcome', 'NEEDS_RECONCILIATION', 'NEEDS_RECONCILIATION'),
  task('completed', 'Produce and independently validate an artifact', 'COMPLETE', 'SUCCEEDED', 'PASSED'),
  task('waiting-capability', 'Hand verified work to the next required capability', 'COMPLETE', 'SUCCEEDED', 'PASSED', true),
]

const batons = tasks.filter((item) => ['completed', 'waiting-capability'].includes(item.task_id)).map((item) => ({
  baton_id: `BATON-${item.task_id}`,
  source_baton_id: 'BATON-PREVIOUS',
  task_id: item.task_id,
  status: 'VERIFIED',
  verification_status: 'VERIFIED',
  verification_reason: 'Canonical completion and evidence verified.',
  validation_id: `validation-${item.task_id}`,
  required_capability: item.fixture_waiting ? 'UI_INTEGRATION' : 'ARCHITECTURAL_AUDIT',
  git_commit: 'fixture-commit',
  dispatch_id: item.fixture_waiting ? `dispatch-${item.task_id}` : null,
  dispatch_status: item.fixture_waiting ? 'WAITING_FOR_CAPABILITY' : null,
  dispatch_reason: item.fixture_waiting ? 'No eligible external target is configured.' : null,
  target_id: null,
}))

const scenario = new URLSearchParams(window.location.search).get('scenario') ?? 'overview'
const selectedByScenario = {
  overview: 'active',
  active: 'active',
  validation_failure: 'validation-failed',
  needs_reconciliation: 'needs-reconciliation',
  completed: 'completed',
  waiting_for_capability: 'waiting-capability',
  stale_unavailable: 'waiting-capability',
}
const receivedAt = Date.now()
const stale = scenario === 'stale_unavailable'
const viewModel = buildOfficeViewModel(mapCanonicalOfficeState({ source: 'canonical_sqlite', tasks, batons }), {
  receivedAt,
  now: receivedAt + (stale ? OFFICE_STALE_AFTER_MS + 1 : 1),
  errorKind: stale ? 'BACKEND_UNAVAILABLE' : null,
  errorMessage: stale ? 'Engineering fixture: backend unavailable after the last successful canonical read.' : null,
})

createRoot(document.getElementById('root')).render(
  <main className="dashboard">
    <header className="dashboard__header">
      <div>
        <h1>AppShak Observability</h1>
        <p>S2A-WP2 engineering baseline: {scenario}</p>
      </div>
    </header>
    <div className="office-view">
      <OfficeWorkflowPanel model={viewModel} selectedTaskId={selectedByScenario[scenario]} />
    </div>
  </main>,
)
