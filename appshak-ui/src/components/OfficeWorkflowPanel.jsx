function shown(value) {
  return value === null || value === undefined || value === '' ? 'UNKNOWN' : String(value)
}

function jsonValue(value) {
  return value && typeof value === 'object' ? JSON.stringify(value, null, 2) : shown(value)
}

function Value({ value, mono = false }) {
  const display = shown(value)
  return <span className={mono ? 'office-workflow__value office-workflow__value--mono' : 'office-workflow__value'} title={display}>{display}</span>
}

function Detail({ label, value, mono = false }) {
  return (
    <div className="office-workflow__detail">
      <dt>{label}</dt>
      <dd><Value value={value} mono={mono} /></dd>
    </div>
  )
}

function State({ value, current = true }) {
  const state = shown(value)
  const modifier = current
    ? `office-workflow__state-chip--${state.toLowerCase().replaceAll('_', '-')}`
    : 'office-workflow__state-chip--history'
  return <span className={`office-workflow__state-chip ${modifier}`}>{state}</span>
}

function Stage({ number, title, state, current = true, children }) {
  return (
    <section className="office-workflow__stage" aria-label={`${title} workflow stage`}>
      <header>
        <span className="office-workflow__stage-number">{number}</span>
        <h4>{title}</h4>
        <State value={state} current={current} />
      </header>
      {children}
    </section>
  )
}

function failureMessage(task) {
  if (task.visual_state === 'NEEDS_RECONCILIATION') {
    return `Outcome uncertain; reconciliation is required. Reason: ${shown(task.attempt_reason ?? task.validation_reason)}`
  }
  if (task.visual_state === 'EXECUTION_FAILED') {
    return `Execution failed before validated completion. Reason: ${shown(task.attempt_reason)}`
  }
  if (task.visual_state === 'VALIDATION_FAILED') {
    return `Execution produced an artifact, but independent validation failed. Reason: ${shown(task.validation_reason)}`
  }
  if (task.visual_state === 'VALIDATION_ERROR') {
    return `The validation process errored; this is not a failed acceptance check. Reason: ${shown(task.validation_reason)}`
  }
  if (task.visual_state === 'UNKNOWN_STATE') {
    return 'Canonical records do not support a verified completion state.'
  }
  return null
}

function AttemptHistory({ attempts, isCurrent }) {
  return (
    <details className="office-workflow__history" open={attempts.length > 1}>
      <summary>Execution chronology ({attempts.length})</summary>
      {attempts.length === 0 ? <p className="event-empty">No execution attempt is recorded.</p> : (
        <ol className="office-workflow__history-list">
          {[...attempts].reverse().map((attempt) => (
            <li key={attempt.attempt_id ?? `attempt-${attempt.created_at}`}>
              <div className="office-workflow__history-head">
                <strong>{attempt.current ? 'CURRENT ATTEMPT' : 'PREVIOUS ATTEMPT'}</strong>
                <State value={attempt.state} current={attempt.current && isCurrent} />
              </div>
              <dl className="office-workflow__details office-workflow__details--compact">
                <Detail label="Attempt ID" value={attempt.attempt_id} mono />
                <Detail label="Agent" value={attempt.agent_id} />
                <Detail label="Operation" value={attempt.requested_operation} />
                <Detail label="Created" value={attempt.created_at} />
                <Detail label="Started" value={attempt.started_at} />
                <Detail label="Updated" value={attempt.updated_at} />
                <Detail label="Return code" value={attempt.return_code} />
                <Detail label="Outcome reason" value={attempt.outcome_reason} />
              </dl>
            </li>
          ))}
        </ol>
      )}
    </details>
  )
}

function ArtifactList({ task }) {
  if (task.artifacts.length === 0) return <p className="event-empty">No artifact is recorded.</p>
  return (
    <div className="office-workflow__records">
      {task.artifacts.map((artifact) => {
        const isValidated = Boolean(task.validation_id) && artifact.artifact_id === task.artifact_id
        return (
          <article key={artifact.artifact_id ?? artifact.reference} className="office-workflow__record">
            <dl className="office-workflow__details office-workflow__details--compact">
              <Detail label="Artifact ID" value={artifact.artifact_id} mono />
              <Detail label="Produced by attempt" value={artifact.attempt_id} mono />
              <Detail label="Reference" value={artifact.reference} mono />
              <Detail label="SHA-256" value={artifact.sha256} mono />
              <Detail label="Size" value={artifact.size_bytes === null ? null : `${artifact.size_bytes} bytes`} />
              <Detail label="Recorded" value={artifact.created_at} />
              {isValidated ? <Detail label="Linkage" value="CURRENT VALIDATION ARTIFACT" /> : null}
            </dl>
          </article>
        )
      })}
    </div>
  )
}

function ValidationHistory({ task, isCurrent }) {
  if (task.validations.length === 0) return <p className="event-empty">No independent validation is recorded.</p>
  return (
    <div className="office-workflow__records">
      {[...task.validations].reverse().map((validation) => (
        <article key={validation.validation_id} className="office-workflow__record">
          <div className="office-workflow__history-head">
            <strong>{validation.current ? 'CURRENT VALIDATION' : 'PREVIOUS VALIDATION'}</strong>
            <State value={validation.status} current={validation.current && isCurrent} />
          </div>
          <dl className="office-workflow__details office-workflow__details--compact">
            <Detail label="Validation ID" value={validation.validation_id} mono />
            <Detail label="Validator" value={validation.validator_id} />
            <Detail label="Artifact validated" value={validation.artifact_id} mono />
            <Detail label="Related attempt" value={validation.related_attempt_id} mono />
            <Detail label="Validated SHA-256" value={validation.validated_sha256} mono />
            <Detail label="Completed" value={validation.completed_at} />
            <Detail label="Reason" value={validation.evidence_reason} />
          </dl>
          {validation.checks.length > 0 ? (
            <details className="office-workflow__evidence">
              <summary>Validation checks and evidence ({validation.checks.length})</summary>
              {validation.checks.map((check) => (
                <div key={check.criterion_id} className="office-workflow__check">
                  <State value={check.status} current={isCurrent} />
                  <Value value={check.criterion_type} />
                  <Value value={check.criterion_id} mono />
                  <pre>Expected: {jsonValue(check.expected)}{`\n`}Observed: {jsonValue(check.evidence)}</pre>
                </div>
              ))}
            </details>
          ) : (
            <pre className="office-workflow__evidence-json">Evidence: {jsonValue(validation.evidence)}</pre>
          )}
        </article>
      ))}
    </div>
  )
}

function TaskInspection({ task, isCurrent }) {
  const failure = failureMessage(task)
  const baton = task.baton
  return (
    <article className={isCurrent ? 'office-workflow__inspection' : 'office-workflow__inspection office-workflow__inspection--stale'}>
      <header className="office-workflow__inspection-head">
        <div>
          <p className="office-workflow__eyebrow">Selected canonical workflow</p>
          <h3>{task.objective}</h3>
          <Value value={task.task_id} mono />
        </div>
        <State value={isCurrent ? task.visual_state : `LAST_KNOWN_${task.visual_state}`} />
      </header>

      {failure ? <p className={`office-workflow__condition office-workflow__condition--${task.visual_state.toLowerCase()}`}>{failure}</p> : null}

      <div className="office-workflow__chain" aria-label="Task workflow chain">
        <Stage number="1" title="Objective" state={task.task_state} current={isCurrent}>
          <p>{task.objective}</p>
          <dl className="office-workflow__details office-workflow__details--compact">
            <Detail label="Raw canonical task state" value={task.task_state} />
            <Detail label="Task ID" value={task.task_id} mono />
            <Detail label="Owner" value={task.owner_id} />
            <Detail label="Authority" value={task.authority_id} mono />
            <Detail label="Source request" value={task.source_request_id} mono />
            <Detail label="Created" value={task.created_at} />
            <Detail label="Updated" value={task.updated_at} />
          </dl>
        </Stage>

        <Stage number="2" title="Assignment" state={task.worker_id ? 'ASSIGNED' : 'UNASSIGNED'} current={isCurrent}>
          <dl className="office-workflow__details office-workflow__details--compact">
            <Detail label="Worker / agent" value={task.worker_id} />
            <Detail label="Workspace" value={task.workspace_id} mono />
            <Detail label="Assignment authority" value={task.assignment_authority_id} mono />
            <Detail label="Assignment source" value={task.assignment_source} mono />
            <Detail label="Assigned" value={task.assigned_at} />
          </dl>
        </Stage>

        <Stage number="3" title="Execution" state={task.attempt_state} current={isCurrent}>
          <AttemptHistory attempts={task.attempts} isCurrent={isCurrent} />
        </Stage>

        <Stage number="4" title="Artifact" state={task.artifact_integrity} current={isCurrent}>
          <ArtifactList task={task} />
        </Stage>

        <Stage number="5" title="Independent validation" state={task.validation_state} current={isCurrent}>
          <ValidationHistory task={task} isCurrent={isCurrent} />
        </Stage>

        <Stage number="6" title="Completion" state={task.visual_state} current={isCurrent}>
          <dl className="office-workflow__details office-workflow__details--compact">
            <Detail label="Raw canonical task state" value={task.task_state} />
            <Detail label="Artifact integrity" value={task.artifact_integrity} />
            <Detail label="Validation matches artifact" value={task.validation_matches_artifact} />
          </dl>
          {task.visual_state === 'COMPLETE' ? <p className="office-workflow__success">Persisted validation and artifact integrity support COMPLETE.</p> : null}
        </Stage>

        <Stage number="7" title="Verified baton" state={task.baton_verification_state} current={isCurrent}>
          <dl className="office-workflow__details office-workflow__details--compact">
            <Detail label="Baton ID" value={baton?.baton_id} mono />
            <Detail label="Baton status" value={baton?.status} />
            <Detail label="Verification" value={baton?.verification_status} />
            <Detail label="Verification reason" value={baton?.verification_reason} />
            <Detail label="Source baton" value={baton?.source_baton_id} mono />
            <Detail label="Validation lineage" value={baton?.validation_id} mono />
            <Detail label="Git basis" value={baton?.git_commit} mono />
            <Detail label="Required capability" value={baton?.required_capability} />
            <Detail label="Next objective" value={baton?.next_objective} />
          </dl>
        </Stage>

        <Stage number="8" title="Routing / handoff" state={task.routing_state} current={isCurrent}>
          <dl className="office-workflow__details office-workflow__details--compact">
            <Detail label="Dispatch ID" value={baton?.dispatch_id} mono />
            <Detail label="Dispatch status" value={baton?.dispatch_status} />
            <Detail label="Selected target" value={baton?.target_id} />
            <Detail label="Routing reason" value={baton?.dispatch_reason} />
            <Detail label="Updated" value={baton?.dispatch_updated_at} />
          </dl>
          {task.routing_state === 'WAITING_FOR_CAPABILITY' ? (
            <p className="office-workflow__waiting">Work is verified and ready for the required capability, but no eligible external target is currently configured. No pickup or dispatch is implied.</p>
          ) : null}
        </Stage>
      </div>
    </article>
  )
}

export function OfficeWorkflowPanel({ model, selectedTaskId = null, onSelectTask = null }) {
  const isCurrent = model.freshness === 'LIVE / CURRENT'
  const selectedTask = model.tasks.find((task) => task.task_id === selectedTaskId) ?? model.tasks[0] ?? null
  const countEntries = Object.entries(model.task_counts ?? {})

  return (
    <section className="panel office-workflow" aria-label="Canonical S1 office workflow">
      <header className="panel__header office-workflow__header">
        <div>
          <p className="office-workflow__eyebrow">Authoritative workflow state</p>
          <h2>Operator Console · S1 Workflow</h2>
          <p>Read-only canonical SQLite projection</p>
        </div>
        <div className="office-workflow__availability" role="status" aria-live="polite">
          <span className={isCurrent ? 'office-workflow__badge office-workflow__badge--current' : 'office-workflow__badge office-workflow__badge--stale'}>
            {model.freshness}
          </span>
          {model.error_state ? <span className="office-workflow__badge office-workflow__badge--error">{model.error_state}</span> : null}
        </div>
      </header>
      <p className="office-workflow__meta">
        Source: {shown(model.source)} · Last successful read: {shown(model.received_at)}
      </p>
      {model.error_message ? <p className="office-workflow__error">{model.error_message}</p> : null}
      {!isCurrent && model.tasks.length > 0 ? (
        <p className="office-workflow__warning">Last-known records only. No current completion or activity is asserted.</p>
      ) : null}

      <section className="office-workflow__overview" aria-label="Canonical task overview">
        <header>
          <div>
            <h3>Task overview</h3>
            <p>Status counts are directly derived and may overlap; every task retains its raw canonical state.</p>
          </div>
          <div className="office-workflow__counts">
            {countEntries.map(([label, count]) => <span key={label}><strong>{count}</strong>{label.replaceAll('_', ' ')}</span>)}
          </div>
        </header>
        {model.tasks.length === 0 ? (
          <p className="event-empty">{isCurrent ? 'No owner tasks exist in this canonical response.' : 'Canonical task state is unavailable.'}</p>
        ) : (
          <div className="office-workflow__task-list" role="list" aria-label="Owner tasks">
            {model.tasks.map((task) => {
              const selected = selectedTask?.task_id === task.task_id
              return (
                <button
                  aria-pressed={selected}
                  className={selected ? 'office-workflow__task-button office-workflow__task-button--selected' : 'office-workflow__task-button'}
                  key={task.task_id}
                  onClick={() => onSelectTask?.(task.task_id)}
                  role="listitem"
                  type="button"
                >
                  <span className="office-workflow__task-summary">
                    <strong>{task.objective}</strong>
                    <small title={task.task_id}>{task.task_id}</small>
                  </span>
                  <span className="office-workflow__task-states">
                    <State value={task.presentation_group} current={isCurrent} />
                    <small>Canonical: {task.task_state}</small>
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </section>

      {selectedTask ? <TaskInspection task={selectedTask} isCurrent={isCurrent} /> : null}
    </section>
  )
}
