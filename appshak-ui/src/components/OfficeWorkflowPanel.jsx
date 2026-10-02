function shown(value) {
  return value === null || value === undefined || value === '' ? 'UNKNOWN' : String(value)
}

function Detail({ label, value }) {
  return (
    <div className="office-workflow__detail">
      <dt>{label}</dt>
      <dd>{shown(value)}</dd>
    </div>
  )
}

export function OfficeWorkflowPanel({ model }) {
  const isCurrent = model.freshness === 'LIVE / CURRENT'
  return (
    <section className="panel office-workflow" aria-label="Canonical S1 office workflow">
      <header className="panel__header office-workflow__header">
        <div>
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
      {model.tasks.length === 0 ? (
        <p className="event-empty">{isCurrent ? 'No owner tasks in this canonical response.' : 'Canonical task state is unavailable.'}</p>
      ) : (
        <div className="office-workflow__tasks">
          {model.tasks.map((task) => (
            <article className={isCurrent ? 'office-workflow__task' : 'office-workflow__task office-workflow__task--stale'} key={task.task_id}>
              <div className="office-workflow__task-head">
                <div>
                  <h3>{task.objective}</h3>
                  <small>Task {task.task_id}</small>
                </div>
                <span className={isCurrent && task.visual_state === 'COMPLETE'
                  ? 'office-workflow__state office-workflow__state--complete'
                  : 'office-workflow__state'}>
                  {isCurrent ? task.visual_state : `LAST KNOWN: ${task.visual_state}`}
                </span>
              </div>
              <dl className="office-workflow__details">
                <Detail label="Task state" value={task.task_state} />
                <Detail label="Assigned worker" value={task.worker_id} />
                <Detail label="Workspace" value={task.workspace_id} />
                <Detail label="Execution attempt" value={task.attempt_id} />
                <Detail label="Execution state" value={task.attempt_state} />
                <Detail label="Artifact ID" value={task.artifact_id} />
                <Detail label="Artifact reference" value={task.artifact_reference} />
                <Detail label="Stored SHA-256" value={task.artifact_sha256} />
                <Detail label="Artifact integrity" value={task.artifact_integrity} />
                <Detail label="Validation" value={task.validation_state} />
                <Detail label="Baton" value={task.baton_id} />
                <Detail label="Baton verification" value={task.baton_verification_state} />
                <Detail label="Required capability" value={task.required_capability} />
                <Detail label="Routing / handoff" value={task.routing_state} />
                <Detail label="Selected target" value={task.selected_target} />
              </dl>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
