PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    type TEXT NOT NULL,
    origin_id TEXT NOT NULL,
    target_agent TEXT,
    payload_json TEXT NOT NULL,
    justification TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    error TEXT,
    correlation_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_status_id
    ON events(status, id);

CREATE INDEX IF NOT EXISTS idx_events_target_status_id
    ON events(target_agent, status, id);

CREATE INDEX IF NOT EXISTS idx_events_corr
    ON events(correlation_id);

CREATE TABLE IF NOT EXISTS leases (
    event_id INTEGER PRIMARY KEY,
    claimed_by TEXT NOT NULL,
    claim_ts TEXT NOT NULL,
    lease_expiry TEXT NOT NULL,
    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_leases_expiry
    ON leases(lease_expiry);

CREATE TABLE IF NOT EXISTS tool_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    working_dir TEXT NOT NULL,
    idempotency_key TEXT,
    allowed INTEGER NOT NULL,
    reason TEXT,
    payload_json TEXT NOT NULL,
    result_json TEXT,
    correlation_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_tool_audit_ts
    ON tool_audit(ts);

CREATE INDEX IF NOT EXISTS idx_tool_audit_idempotency
    ON tool_audit(idempotency_key);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    idempotency_key TEXT PRIMARY KEY,
    created_ts TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    event_id INTEGER,
    result_json TEXT
);

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    agent_id TEXT PRIMARY KEY,
    consumer_id TEXT NOT NULL,
    pid INTEGER NOT NULL,
    ts TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_ts
    ON worker_heartbeats(ts);

CREATE TABLE IF NOT EXISTS owner_tasks (
    task_id TEXT PRIMARY KEY,
    source_request_id TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    authority_id TEXT NOT NULL,
    state TEXT NOT NULL,
    assigned_agent TEXT,
    workspace_id TEXT,
    assignment_authority_id TEXT,
    assignment_source TEXT,
    assigned_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS owner_task_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES owner_tasks(task_id),
    event_type TEXT NOT NULL,
    previous_state TEXT,
    new_state TEXT NOT NULL,
    ts TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    attempt_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_owner_task_history_task_id
    ON owner_task_history(task_id, id);

CREATE TABLE IF NOT EXISTS execution_attempts (
    attempt_id TEXT PRIMARY KEY,
    source_request_id TEXT NOT NULL UNIQUE,
    source_event_id INTEGER,
    idempotency_key TEXT NOT NULL UNIQUE,
    authority_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    requested_operation TEXT NOT NULL,
    task_id TEXT REFERENCES owner_tasks(task_id),
    validation_id TEXT,
    created_at TEXT NOT NULL,
    request_json TEXT NOT NULL,
    state TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 0,
    owner_id TEXT,
    lease_expiry TEXT,
    started_at TEXT,
    outcome_json TEXT,
    audit_id INTEGER,
    published_event_id INTEGER,
    acknowledged_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_execution_attempts_state_lease
    ON execution_attempts(state, lease_expiry);

CREATE TABLE IF NOT EXISTS owner_task_artifacts (
    artifact_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL REFERENCES owner_tasks(task_id),
    attempt_id TEXT NOT NULL REFERENCES execution_attempts(attempt_id),
    kind TEXT NOT NULL,
    reference TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    producer_id TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(task_id, attempt_id, reference)
);

CREATE TABLE IF NOT EXISTS task_acceptance_criteria (
    criterion_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES owner_tasks(task_id),
    criterion_type TEXT NOT NULL,
    config_json TEXT NOT NULL,
    required INTEGER NOT NULL DEFAULT 1,
    source_ref TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_acceptance_criteria_task
    ON task_acceptance_criteria(task_id, created_at);

CREATE TABLE IF NOT EXISTS validation_runs (
    validation_id TEXT PRIMARY KEY,
    source_request_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL REFERENCES owner_tasks(task_id),
    artifact_id TEXT NOT NULL,
    validator_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    related_attempt_id TEXT REFERENCES execution_attempts(attempt_id),
    validated_sha256 TEXT,
    validated_size_bytes INTEGER,
    evidence_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_validation_runs_task
    ON validation_runs(task_id, created_at);

CREATE TABLE IF NOT EXISTS validation_checks (
    validation_id TEXT NOT NULL REFERENCES validation_runs(validation_id),
    criterion_id TEXT NOT NULL REFERENCES task_acceptance_criteria(criterion_id),
    status TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    PRIMARY KEY(validation_id, criterion_id)
);

CREATE TABLE IF NOT EXISTS capability_batons (
    baton_id TEXT PRIMARY KEY,
    source_baton_id TEXT,
    task_id TEXT NOT NULL,
    work_package TEXT NOT NULL,
    next_objective TEXT NOT NULL DEFAULT '',
    repository_root TEXT NOT NULL,
    git_commit TEXT NOT NULL,
    working_tree_hash TEXT NOT NULL DEFAULT '',
    completion_status TEXT NOT NULL,
    current_state_json TEXT NOT NULL,
    results_json TEXT NOT NULL DEFAULT '{}',
    evidence_json TEXT NOT NULL,
    validation_id TEXT,
    required_capability TEXT NOT NULL,
    created_at TEXT NOT NULL,
    producer_id TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    status TEXT NOT NULL,
    verification_reason TEXT,
    verification_evidence_json TEXT,
    policy_version TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_capability_batons_status
    ON capability_batons(status, required_capability);

CREATE UNIQUE INDEX IF NOT EXISTS idx_capability_batons_verified_successor
    ON capability_batons(source_baton_id)
    WHERE source_baton_id IS NOT NULL AND status = 'VERIFIED';

CREATE TABLE IF NOT EXISTS baton_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    baton_id TEXT NOT NULL REFERENCES capability_batons(baton_id),
    event_type TEXT NOT NULL,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    evidence_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_baton_history_baton
    ON baton_history(baton_id, id);

CREATE TABLE IF NOT EXISTS baton_dispatches (
    dispatch_id TEXT PRIMARY KEY,
    baton_id TEXT NOT NULL UNIQUE REFERENCES capability_batons(baton_id),
    required_capability TEXT NOT NULL,
    status TEXT NOT NULL,
    target_id TEXT,
    route_json TEXT,
    context_json TEXT NOT NULL,
    reason TEXT,
    handoff_task_id TEXT REFERENCES owner_tasks(task_id),
    attempt_id TEXT REFERENCES execution_attempts(attempt_id),
    payload_reference TEXT,
    result_reference TEXT,
    workspace_root TEXT,
    credential_sha256 TEXT,
    chief_authorized_by TEXT,
    pickup_owner_id TEXT,
    pickup_generation INTEGER,
    dispatched_at TEXT,
    acknowledged_at TEXT,
    result_at TEXT,
    result_sha256 TEXT,
    result_size_bytes INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_baton_dispatches_status
    ON baton_dispatches(status, required_capability);
