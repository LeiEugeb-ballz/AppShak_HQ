import React, { useEffect, useRef } from 'react'
import { createRoot } from 'react-dom/client'
import '../src/index.css'
import '../src/App.css'
import { OfficeAnimator } from '../src/office/animator.js'
import { createOfficeSceneRenderer } from '../src/office/scene.js'
import { buildOfficeViewModel, mapCanonicalOfficeState, OFFICE_STALE_AFTER_MS } from '../src/office/officeState.js'

function task(id, state, attemptState, validationState = null, baton = false) {
  const artifact = attemptState === 'SUCCEEDED' ? [{ artifact_id: `artifact-${id}`, attempt_id: `attempt-${id}`, reference: 'output.txt', sha256: `sha-${id}`, size_bytes: 10 }] : []
  return { task_id: id, objective: `S2B visual fixture: ${id}`, state, assigned_agent: 'command', workspace_id: 'fixture-workspace', attempts: [{ attempt_id: `attempt-${id}`, state: attemptState }], artifacts: artifact, criteria: [{ criterion_id: `criterion-${id}`, criterion_type: 'FILE_EXISTS', required: true }], validations: validationState ? [{ validation_id: `validation-${id}`, status: validationState, artifact_id: `artifact-${id}`, validated_sha256: validationState === 'PASSED' ? `sha-${id}` : null, evidence: validationState === 'FAILED' ? { reason: 'fixture validation failed' } : { integrity_match: true }, checks: [] }] : [],
    ...(baton ? { baton: true } : {}),
  }
}

const scenario = new URLSearchParams(window.location.search).get('scenario') ?? 'active'
const states = {
  active: task('active', 'EXECUTING', 'RUNNING'),
  validation_failed: task('validation-failed', 'VALIDATION_FAILED', 'SUCCEEDED', 'FAILED'),
  needs_reconciliation: task('needs-reconciliation', 'NEEDS_RECONCILIATION', 'NEEDS_RECONCILIATION'),
  complete: task('complete', 'COMPLETE', 'SUCCEEDED', 'PASSED'),
  waiting_for_capability: task('waiting', 'COMPLETE', 'SUCCEEDED', 'PASSED', true),
  stale_unavailable: task('stale', 'COMPLETE', 'SUCCEEDED', 'PASSED', true),
}
const selected = states[scenario] ?? states.active
const rawTask = { ...selected }
delete rawTask.baton
const raw = { source: 'canonical_sqlite', tasks: [rawTask], batons: selected.baton ? [{ baton_id: 'BATON-fixture', task_id: selected.task_id, status: 'VERIFIED', verification_status: 'VERIFIED', dispatch_status: 'WAITING_FOR_CAPABILITY', target_id: null }] : [] }
const receivedAt = Date.now()
const model = buildOfficeViewModel(mapCanonicalOfficeState(raw), { receivedAt, now: receivedAt + (scenario === 'stale_unavailable' ? OFFICE_STALE_AFTER_MS + 1 : 1), errorKind: scenario === 'stale_unavailable' ? 'BACKEND_UNAVAILABLE' : null, errorMessage: scenario === 'stale_unavailable' ? 'Fixture: backend unavailable' : null })

export function Fixture() {
  const canvasRef = useRef(null)
  useEffect(() => {
    const renderer = createOfficeSceneRenderer(canvasRef.current)
    const animator = new OfficeAnimator()
    animator.ingestOfficeModel(model)
    renderer.render({ animationState: animator.tick(1000), officeModel: model, connectionState: 'fixture' })
    return () => renderer.destroy()
  }, [])
  return <main className="dashboard"><header className="dashboard__header"><div><h1>AppShak Office · S2B</h1><p>ATS projection fixture: {scenario}</p></div></header><div className="office-view"><div className="office-view__canvas-shell"><canvas ref={canvasRef} className="office-view__canvas" aria-label={`S2B ${scenario} office baseline`} /></div></div></main>
}

createRoot(document.getElementById('root')).render(<Fixture />)
