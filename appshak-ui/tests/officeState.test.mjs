import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import react from '@vitejs/plugin-react'
import {
  buildOfficeViewModel,
  mapCanonicalOfficeState,
  OFFICE_STALE_AFTER_MS,
} from '../src/office/officeState.js'

const uiRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
let vite
let OfficeWorkflowPanel

before(async () => {
  vite = await createServer({
    configFile: false,
    root: uiRoot,
    plugins: [react()],
    optimizeDeps: { noDiscovery: true, entries: [] },
    server: { middlewareMode: true },
    appType: 'custom',
  })
  ;({ OfficeWorkflowPanel } = await vite.ssrLoadModule('/src/components/OfficeWorkflowPanel.jsx'))
})

after(async () => {
  await vite?.close()
})

function taskRow({
  id = 'task-123', objective = 'Write verified artifact', taskState = 'COMPLETE',
  attemptState = 'SUCCEEDED', validationState = 'PASSED', baton = true,
} = {}) {
  const artifact = attemptState === 'SUCCEEDED'
    ? [{ artifact_id: `artifact-${id}`, attempt_id: `attempt-${id}`, reference: 'output.txt',
      size_bytes: 12, sha256: `hash-${id}`, created_at: '2026-01-01T00:02:00Z' }]
    : []
  return {
    task: {
      task_id: id, source_request_id: `request-${id}`, owner_id: 'owner', objective,
      authority_id: `authority-${id}`, state: taskState, assigned_agent: 'command',
      workspace_id: 'workspaces/command', assignment_authority_id: `authority-${id}`,
      assignment_source: `assignment-${id}`, assigned_at: '2026-01-01T00:00:30Z',
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:04:00Z',
      attempts: [{ attempt_id: `attempt-${id}`, state: attemptState, agent_id: 'command',
        requested_operation: 'write_file', created_at: '2026-01-01T00:01:00Z',
        updated_at: '2026-01-01T00:02:00Z', outcome: attemptState === 'FAILED'
          ? { reason: 'tool returned non-zero', return_code: 2 } : { return_code: 0 } }],
      artifacts: artifact,
      criteria: [{ criterion_id: `criterion-${id}`, criterion_type: 'FILE_EXISTS',
        config: {}, required: true, source_ref: `criterion-source-${id}` }],
      validations: validationState ? [{ validation_id: `validation-${id}`, status: validationState,
        artifact_id: `artifact-${id}`, validator_id: 'deterministic-validator',
        related_attempt_id: `validator-attempt-${id}`,
        validated_sha256: validationState === 'PASSED' ? `hash-${id}` : null,
        evidence: validationState === 'FAILED' ? { reason: 'expected digest did not match' } : { integrity_match: true },
        completed_at: '2026-01-01T00:03:00Z', checks: [{ criterion_id: `criterion-${id}`,
          criterion_type: 'FILE_EXISTS', status: validationState, required: true,
          expected: {}, evidence: { criterion_type: 'FILE_EXISTS', observed: { exists: true } } }] }] : [],
    },
    baton: baton ? { baton_id: `BATON-${id}`, source_baton_id: 'BATON-PREVIOUS', task_id: id,
      status: 'VERIFIED', verification_status: 'VERIFIED', verification_reason: 'Canonical evidence passed.',
      required_capability: 'UI_INTEGRATION', validation_id: `validation-${id}`,
      git_commit: 'abc123', dispatch_id: `dispatch-${id}`, dispatch_status: 'WAITING_FOR_CAPABILITY',
      dispatch_reason: 'No eligible target configured.', target_id: null } : null,
  }
}

function payload(options = {}) {
  const row = taskRow(options)
  return { source: 'canonical_sqlite', tasks: [row.task], batons: row.baton ? [row.baton] : [] }
}

function multiPayload() {
  const rows = [
    taskRow({ id: 'active', objective: 'Active work', taskState: 'EXECUTING', attemptState: 'RUNNING', validationState: null, baton: false }),
    taskRow({ id: 'waiting', objective: 'Waiting work', taskState: 'ASSIGNED', attemptState: 'PENDING', validationState: null, baton: false }),
    taskRow({ id: 'validating', objective: 'Validation work', taskState: 'VALIDATING', validationState: 'RUNNING', baton: false }),
    taskRow({ id: 'complete', objective: 'Completed work' }),
    taskRow({ id: 'failed', objective: 'Failed validation', taskState: 'VALIDATION_FAILED', validationState: 'FAILED', baton: false }),
    taskRow({ id: 'uncertain', objective: 'Uncertain work', taskState: 'NEEDS_RECONCILIATION', attemptState: 'NEEDS_RECONCILIATION', validationState: null, baton: false }),
  ]
  return { source: 'canonical_sqlite', tasks: rows.map((row) => row.task), batons: rows.flatMap((row) => row.baton ? [row.baton] : []) }
}

function model(raw, options = {}) {
  return buildOfficeViewModel(mapCanonicalOfficeState(raw), {
    receivedAt: 10_000, now: 10_001, ...options,
  })
}

function render(viewModel, selectedTaskId = null) {
  return renderToStaticMarkup(React.createElement(OfficeWorkflowPanel, { model: viewModel, selectedTaskId }))
}

test('canonical IDs, states, digests, and nullable target map without invention', () => {
  const task = model(payload()).tasks[0]
  assert.equal(task.task_id, 'task-123')
  assert.equal(task.task_state, 'COMPLETE')
  assert.equal(task.attempt_id, 'attempt-task-123')
  assert.equal(task.artifact_id, 'artifact-task-123')
  assert.equal(task.artifact_integrity, 'MATCHES_PERSISTED_VALIDATION')
  assert.equal(task.validation_state, 'PASSED')
  assert.equal(task.baton_verification_state, 'VERIFIED')
  assert.equal(task.routing_state, 'WAITING_FOR_CAPABILITY')
  assert.equal(task.selected_target, null)
})

test('task overview groups directly-derived states and preserves raw canonical state', () => {
  const view = model(multiPayload())
  assert.equal(view.task_counts.TOTAL, 6)
  assert.equal(view.task_counts.ACTIVE, 1)
  assert.equal(view.task_counts.WAITING, 1)
  assert.equal(view.task_counts.VALIDATING, 1)
  assert.equal(view.task_counts.COMPLETE, 1)
  assert.equal(view.task_counts.FAILED, 1)
  assert.equal(view.task_counts.NEEDS_RECONCILIATION, 1)
  const html = render(view)
  assert.match(html, /Task overview/)
  assert.match(html, /may overlap/)
  assert.match(html, /Canonical: EXECUTING/)
  assert.match(html, /Raw canonical task state/)
})

test('validated COMPLETE and truthful waiting handoff render from canonical rows', () => {
  const view = model(payload())
  const html = render(view)
  assert.equal(view.tasks[0].visual_state, 'COMPLETE')
  assert.match(html, /office-workflow__state-chip--complete/)
  assert.match(html, /WAITING_FOR_CAPABILITY/)
  assert.match(html, /no eligible external target is currently configured/i)
  assert.match(html, /No pickup or dispatch is implied/)
})

test('successful execution without independent validation does not render COMPLETE', () => {
  const view = model(payload({ taskState: 'READY_FOR_VALIDATION', validationState: null }))
  assert.equal(view.tasks[0].attempt_state, 'SUCCEEDED')
  assert.equal(view.tasks[0].artifact_integrity, 'RECORDED_UNVALIDATED')
  assert.equal(view.tasks[0].visual_state, 'READY_FOR_VALIDATION')
  assert.doesNotMatch(render(view), /office-workflow__state-chip--complete/)
})

test('validation failure is distinct from execution failure', () => {
  const validation = model(payload({ taskState: 'VALIDATION_FAILED', validationState: 'FAILED', baton: false }))
  const execution = model(payload({ taskState: 'EXECUTION_FAILED', attemptState: 'FAILED', validationState: null, baton: false }))
  assert.equal(validation.tasks[0].visual_state, 'VALIDATION_FAILED')
  assert.equal(execution.tasks[0].visual_state, 'EXECUTION_FAILED')
  assert.match(render(validation), /independent validation failed/)
  assert.match(render(execution), /Execution failed before validated completion/)
})

test('NEEDS_RECONCILIATION remains uncertainty rather than generic failure', () => {
  const view = model(payload({ taskState: 'NEEDS_RECONCILIATION', attemptState: 'NEEDS_RECONCILIATION', validationState: null, baton: false }))
  assert.equal(view.tasks[0].visual_state, 'NEEDS_RECONCILIATION')
  assert.match(render(view), /Outcome uncertain; reconciliation is required/)
  assert.doesNotMatch(render(view), /Execution failed before/)
})

test('current attempt is visibly distinct from attempt history', () => {
  const raw = payload({ taskState: 'EXECUTING', attemptState: 'RUNNING', validationState: null, baton: false })
  raw.tasks[0].attempts.unshift({ attempt_id: 'attempt-old', state: 'FAILED', outcome: { reason: 'first attempt failed' } })
  const view = model(raw)
  assert.equal(view.tasks[0].attempts[0].current, false)
  assert.equal(view.tasks[0].attempts[1].current, true)
  const html = render(view)
  assert.match(html, /CURRENT ATTEMPT/)
  assert.match(html, /PREVIOUS ATTEMPT/)
  assert.match(html, /first attempt failed/)
})

test('artifact and validation linkage with checks and evidence is inspectable', () => {
  const task = model(payload()).tasks[0]
  assert.equal(task.validations[0].artifact_id, task.artifact_id)
  assert.equal(task.validation_matches_artifact, true)
  const html = render(model(payload()))
  assert.match(html, /CURRENT VALIDATION ARTIFACT/)
  assert.match(html, /Validation checks and evidence/)
  assert.match(html, /Observed:/)
})

test('task selection is local, keyboard-accessible, and has no operational network path', async () => {
  const panel = await readFile(path.join(uiRoot, 'src/components/OfficeWorkflowPanel.jsx'), 'utf8')
  const office = await readFile(path.join(uiRoot, 'src/views/OfficeView.jsx'), 'utf8')
  assert.match(office, /setSelectedWorkflowTaskId/)
  assert.match(panel, /onSelectTask\?\.\(task\.task_id\)/)
  assert.match(panel, /type="button"/)
  assert.match(panel, /aria-pressed=/)
  assert.doesNotMatch(panel, /fetch\(|XMLHttpRequest|WebSocket/)
})

test('canonical workflow network code permits GET only', async () => {
  const hook = await readFile(path.join(uiRoot, 'src/hooks/useOfficeState.js'), 'utf8')
  const panel = await readFile(path.join(uiRoot, 'src/components/OfficeWorkflowPanel.jsx'), 'utf8')
  const combined = `${hook}\n${panel}`
  assert.match(hook, /method:\s*'GET'/)
  assert.doesNotMatch(combined, /method:\s*['"](?:POST|PUT|PATCH|DELETE)['"]/i)
  assert.doesNotMatch(combined, /approve|force complete|trigger validation|dispatch baton/i)
})

test('telemetry remains semantically separate from canonical workflow truth', async () => {
  const office = await readFile(path.join(uiRoot, 'src/views/OfficeView.jsx'), 'utf8')
  const panel = await readFile(path.join(uiRoot, 'src/components/OfficeWorkflowPanel.jsx'), 'utf8')
  assert.match(panel, /Authoritative workflow state/)
  assert.match(office, /Telemetry \/ Events \/ Observability/)
  assert.match(office, /Non-authoritative operational signals/)
})

test('stale last-known completion loses current completion styling', () => {
  const view = model(payload(), { now: 10_000 + OFFICE_STALE_AFTER_MS + 1 })
  const html = render(view)
  assert.equal(view.freshness, 'STALE')
  assert.equal(view.scene_status, 'STALE')
  assert.match(html, /LAST_KNOWN_COMPLETE/)
  assert.match(html, /Last-known records only/)
  assert.doesNotMatch(html, /office-workflow__state-chip--complete/)
})

test('backend unavailable and projection error remain distinct', () => {
  const canonical = mapCanonicalOfficeState(payload())
  for (const errorKind of ['BACKEND_UNAVAILABLE', 'PROJECTION_ERROR']) {
    const view = buildOfficeViewModel(canonical, {
      receivedAt: 10_000, now: 10_001, errorKind, errorMessage: 'Read failed',
    })
    assert.equal(view.freshness, 'STALE')
    assert.equal(view.availability, errorKind)
    assert.match(render(view), new RegExp(errorKind))
    assert.doesNotMatch(render(view), /office-workflow__state-chip--complete/)
  }
})

test('long identifiers remain fully available through title text', () => {
  const longId = `task-${'x'.repeat(120)}`
  const html = render(model(payload({ id: longId })))
  assert.match(html, new RegExp(`title="${longId}"`))
  assert.match(html, new RegExp(longId))
})

test('empty and unknown canonical states render safely', () => {
  const empty = model({ source: 'canonical_sqlite', tasks: [], batons: [] })
  assert.match(render(empty), /No owner tasks exist/)
  const unavailable = buildOfficeViewModel(null, { errorKind: 'BACKEND_UNAVAILABLE' })
  assert.equal(unavailable.freshness, 'UNKNOWN_STATE')
  assert.equal(unavailable.scene_status, 'BACKEND_UNAVAILABLE')
  assert.match(render(unavailable), /Canonical task state is unavailable/)
})

test('noncanonical response fails closed', () => {
  assert.throws(() => mapCanonicalOfficeState({ source: 'mock', tasks: [], batons: [] }))
  assert.throws(() => mapCanonicalOfficeState({ source: 'canonical_sqlite', tasks: [{}], batons: [] }))
})
