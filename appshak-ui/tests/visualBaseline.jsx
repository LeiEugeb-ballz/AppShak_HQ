import React from 'react'
import { createRoot } from 'react-dom/client'
import '../src/index.css'
import '../src/App.css'
import { OfficeWorkflowPanel } from '../src/components/OfficeWorkflowPanel'
import { buildOfficeViewModel, mapCanonicalOfficeState, OFFICE_STALE_AFTER_MS } from '../src/office/officeState'

// Isolated visual test fixtures. Production App.jsx never imports this file.
const scenario = new URLSearchParams(window.location.search).get('scenario') ?? 'active'
const cases = {
  active: { task: 'EXECUTING', attempt: 'RUNNING', validation: null, baton: false },
  validating: { task: 'VALIDATING', attempt: 'SUCCEEDED', validation: 'RUNNING', baton: false },
  completed: { task: 'COMPLETE', attempt: 'SUCCEEDED', validation: 'PASSED', baton: false },
  failed: { task: 'VALIDATION_FAILED', attempt: 'SUCCEEDED', validation: 'FAILED', baton: false },
  waiting: { task: 'COMPLETE', attempt: 'SUCCEEDED', validation: 'PASSED', baton: true },
  stale_error: { task: 'COMPLETE', attempt: 'SUCCEEDED', validation: 'PASSED', baton: true },
}
const selected = cases[scenario] ?? cases.active
const hasArtifact = selected.attempt === 'SUCCEEDED'
const raw = {
  source: 'canonical_sqlite',
  tasks: [{
    task_id: 'visual-fixture-task-001',
    objective: 'Produce and independently validate one controlled artifact',
    state: selected.task,
    assigned_agent: 'command',
    workspace_id: 'workspaces/command',
    attempts: [{ attempt_id: 'visual-fixture-attempt-001', state: selected.attempt }],
    artifacts: hasArtifact ? [{ artifact_id: 'visual-fixture-artifact-001', reference: 'output.txt',
      size_bytes: 12, sha256: 'fixture-sha256' }] : [],
    validations: selected.validation ? [{ validation_id: 'visual-fixture-validation-001',
      status: selected.validation, artifact_id: 'visual-fixture-artifact-001',
      validated_sha256: selected.validation === 'PASSED' ? 'fixture-sha256' : null }] : [],
  }],
  batons: selected.baton ? [{ baton_id: 'visual-fixture-baton-001', task_id: 'visual-fixture-task-001',
    status: 'VERIFIED', verification_status: 'VERIFIED', required_capability: 'UI_INTEGRATION',
    dispatch_id: 'visual-fixture-dispatch-001', dispatch_status: 'WAITING_FOR_CAPABILITY',
    target_id: null }] : [],
}
const receivedAt = Date.now()
const isStale = scenario === 'stale_error'
const model = buildOfficeViewModel(mapCanonicalOfficeState(raw), {
  receivedAt,
  now: receivedAt + (isStale ? OFFICE_STALE_AFTER_MS + 1 : 1),
  errorKind: isStale ? 'BACKEND_UNAVAILABLE' : null,
  errorMessage: isStale ? 'Visual fixture: backend unavailable after last successful read' : null,
})

createRoot(document.getElementById('root')).render(
  <main className="dashboard">
    <header className="dashboard__header">
      <div>
        <h1>AppShak Observability</h1>
        <p>S2A-WP1 isolated visual fixture: {scenario}</p>
      </div>
    </header>
    <div className="office-view">
      <OfficeWorkflowPanel model={model} />
    </div>
  </main>,
)
