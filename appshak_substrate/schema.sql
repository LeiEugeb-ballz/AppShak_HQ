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
