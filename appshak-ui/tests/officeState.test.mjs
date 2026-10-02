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

function payload(taskState = 'COMPLETE', validationState = 'PASSED', attemptState = 'SUCCEEDED') {
  return {
    source: 'canonical_sqlite',
    tasks: [{
      task_id: 'task-123', objective: 'Write verified artifact', state: taskState,
      assigned_agent: 'command', workspace_id: 'workspaces/command',
      attempts: [{ attempt_id: 'attempt-123', state: attemptState }],
      artifacts: [{ artifact_id: 'artifact-123', reference: 'output.txt', size_bytes: 12, sha256: 'hash-123' }],
      validations: validationState ? [{ validation_id: 'validation-123', status: validationState,
        artifact_id: 'artifact-123', validated_sha256: 'hash-123' }] : [],
    }],
    batons: [{ baton_id: 'BATON-123', task_id: 'task-123', status: 'VERIFIED',
      verification_status: 'VERIFIED', required_capability: 'UI_INTEGRATION',
      dispatch_id: 'dispatch-123', dispatch_status: 'WAITING_FOR_CAPABILITY', target_id: null }],
  }
}

function model(raw, options = {}) {
  return buildOfficeViewModel(mapCanonicalOfficeState(raw), {
    receivedAt: 10_000, now: 10_001, ...options,
  })
}

function render(viewModel) {
  return renderToStaticMarkup(React.createElement(OfficeWorkflowPanel, { model: viewModel }))
}

test('canonical IDs, states, digests, and nullable target map without invention', () => {
  const task = model(payload()).tasks[0]
  assert.equal(task.task_id, 'task-123')
  assert.equal(task.objective, 'Write verified artifact')
  assert.equal(task.worker_id, 'command')
  assert.equal(task.workspace_id, 'workspaces/command')
  assert.equal(task.attempt_id, 'attempt-123')
  assert.equal(task.attempt_state, 'SUCCEEDED')
  assert.equal(task.artifact_id, 'artifact-123')
  assert.equal(task.artifact_reference, 'output.txt')
  assert.equal(task.artifact_sha256, 'hash-123')
  assert.equal(task.artifact_integrity, 'MATCHES_PERSISTED_VALIDATION')
  assert.equal(task.validation_state, 'PASSED')
  assert.equal(task.baton_id, 'BATON-123')
  assert.equal(task.baton_verification_state, 'VERIFIED')
  assert.equal(task.required_capability, 'UI_INTEGRATION')
  assert.equal(task.routing_state, 'WAITING_FOR_CAPABILITY')
  assert.equal(task.selected_target, null)
})

test('validated COMPLETE and waiting handoff render from canonical rows', () => {
  const view = model(payload())
  const html = render(view)
  assert.equal(view.tasks[0].visual_state, 'COMPLETE')
  assert.match(html, /office-workflow__state--complete/)
  assert.match(html, /WAITING_FOR_CAPABILITY/)
  assert.match(html, /UNKNOWN<\/dd>/) // no fabricated selected target
})

test('successful execution without independent validation does not render COMPLETE', () => {
  const view = model(payload('READY_FOR_VALIDATION', null))
  assert.equal(view.tasks[0].attempt_state, 'SUCCEEDED')
  assert.equal(view.tasks[0].artifact_integrity, 'RECORDED_UNVALIDATED')
  assert.equal(view.tasks[0].visual_state, 'READY_FOR_VALIDATION')
  assert.doesNotMatch(render(view), /office-workflow__state--complete/)
})

test('failed validation and inconsistent completion never render COMPLETE', () => {
  const failed = model(payload('VALIDATION_FAILED', 'FAILED'))
  assert.equal(failed.tasks[0].visual_state, 'VALIDATION_FAILED')
  assert.doesNotMatch(render(failed), /office-workflow__state--complete/)
  const inconsistent = model(payload('COMPLETE', null))
  assert.equal(inconsistent.tasks[0].visual_state, 'UNKNOWN_STATE')
  assert.doesNotMatch(render(inconsistent), /office-workflow__state--complete/)
})

test('unknown execution remains visibly unresolved', () => {
  const raw = payload('NEEDS_RECONCILIATION', null, 'NEEDS_RECONCILIATION')
  raw.batons = []
  const view = model(raw)
  assert.equal(view.tasks[0].visual_state, 'NEEDS_RECONCILIATION')
  assert.match(render(view), /NEEDS_RECONCILIATION/)
  assert.doesNotMatch(render(view), /office-workflow__state--complete/)
})

test('stale last-known completion loses current/success styling', () => {
  const view = model(payload(), { now: 10_000 + OFFICE_STALE_AFTER_MS + 1 })
  const html = render(view)
  assert.equal(view.freshness, 'STALE')
  assert.equal(view.scene_status, 'STALE')
  assert.match(html, /LAST KNOWN: COMPLETE/)
  assert.doesNotMatch(html, /office-workflow__state--complete/)
})

test('backend unavailable and projection error are visible and never healthy', () => {
  const canonical = mapCanonicalOfficeState(payload())
  for (const errorKind of ['BACKEND_UNAVAILABLE', 'PROJECTION_ERROR']) {
    const view = buildOfficeViewModel(canonical, {
      receivedAt: 10_000, now: 10_001, errorKind, errorMessage: 'Read failed',
    })
    assert.equal(view.freshness, 'STALE')
    assert.equal(view.availability, errorKind)
    assert.match(render(view), new RegExp(errorKind))
    assert.doesNotMatch(render(view), /office-workflow__state--complete/)
  }
  const empty = buildOfficeViewModel(null, { errorKind: 'BACKEND_UNAVAILABLE' })
  assert.equal(empty.freshness, 'UNKNOWN_STATE')
  assert.equal(empty.scene_status, 'BACKEND_UNAVAILABLE')
})

test('noncanonical response fails closed', () => {
  assert.throws(() => mapCanonicalOfficeState({ source: 'mock', tasks: [], batons: [] }))
  assert.throws(() => mapCanonicalOfficeState({ source: 'canonical_sqlite', tasks: [{}], batons: [] }))
})

test('office UI uses a GET-only read path and exposes no mutation handler', async () => {
  const hook = await readFile(path.join(uiRoot, 'src/hooks/useOfficeState.js'), 'utf8')
  const panel = await readFile(path.join(uiRoot, 'src/components/OfficeWorkflowPanel.jsx'), 'utf8')
  assert.match(hook, /method:\s*'GET'/)
  assert.doesNotMatch(hook, /method:\s*'(POST|PUT|PATCH|DELETE)'/)
  assert.doesNotMatch(panel, /fetch\(|onClick=|onSubmit=/)
})
