# S1-WP1 Runtime Stabilization

Status: **PASS_WITH_NONBLOCKING_FINDINGS**  
Work package: S1-WP1 — Preserve workspaces and bind execution authority  
Starting commit: \`41024a926d1afe226c7dfbac8158c5aa0d12e6b0\`  
Repository: \`E:\AppShak_HQ\`

## Original unsafe behavior

\`WorkspaceManager.ensure_worktrees\` reset every existing workspace with \`git reset --hard\`, \`git clean -fd\`, and \`_ensure_clean\` could escalate to \`git clean -fdx\`, even when \`reset_on_ensure\` was false. The normal \`run_swarm --worktrees\` startup therefore could discard dirty, untracked, or ignored worker state.

The explicit reset path also attempted to check out the baseline branch inside a linked worktree. That can fail because the baseline branch is already checked out by the repository's main worktree.

Tool requests previously carried worker/action/workdir and a legacy \`authorized_by\` label. The gateway did not require an attributable authority record containing a source reference, workspace identity, operation, and creation time. Audit payloads therefore could not establish the full requested relationship between an authority, worker, operation, and workspace.

## Implementation made

### Workspace preservation

Normal \`ensure_worktrees\` now:

- creates a missing worktree when needed;
- validates an existing path with \`git rev-parse --show-toplevel\`;
- verifies that the path is registered by \`git worktree list --porcelain\`;
- reuses a valid existing worktree without reset, checkout, clean, or content mutation;
- preserves dirty and untracked state;
- raises \`WorkspaceStateError\` with an explicit refusal when an existing path is not a usable registered worktree.

Destructive behavior remains behind the existing explicit \`reset_on_ensure=True\` / \`--reset-worktrees\` opt-in. The explicit reset now uses \`git reset --hard <baseline>\` followed by \`git clean -fd\`; it does not attempt to check out a branch already used by the main worktree.

No destructive command was run against the canonical repository or any pre-existing real worker workspace. All destructive-mode tests use temporary repositories and worktrees.

### Execution-authority contract

\`ToolRequest\` now carries:

- \`authority_id\`
- \`source_request_id\`
- \`workspace_id\`
- \`requested_operation\`
- \`created_at\`
- existing \`agent_id\` as the worker identity

Before policy execution, \`ToolGateway.execute\` requires all fields, rejects display-label authority IDs such as \`approved\`, \`authorized\`, \`validated\`, \`admin\`, \`chief\`, or \`command\`, checks that:

- \`workspace_id\` equals the deterministic identity of the registered worker worktree;
- \`requested_operation\` equals the actual action type;
- \`created_at\` is ISO-8601.

Missing or inconsistent authority returns a denial and creates a durable tool-audit record. No privileged authority is synthesized. Valid authority fields are included in the durable audit payload together with the worker, operation, workspace, source request and idempotency key.

\`AgentRuntime\` propagates authority fields from the durable event/request envelope. It may derive only the source request reference and creation time from the existing event ID/timestamp; it never invents \`authority_id\` or \`workspace_id\`.

The existing Chief policy check remains in force. This package records and validates attribution; it does not add a task/approval registry or change model/provider behavior.

## Files changed

Production/runtime:

- \`appshak_substrate/workspace_manager.py\`
- \`appshak_substrate/types.py\`
- \`appshak_substrate/tool_gateway.py\`
- \`appshak_substrate/agent_runtime.py\`
- \`appshak_substrate/chambers/chamber_c_tool_enforcement.py\`

Tests:

- \`tests/test_tool_gateway_enforcement.py\`
- \`tests/test_s1_wp1_workspace_authority.py\`

Documentation and baton files are listed in the handoff baton.

No frontend, schema, provider, model-routing, task, validation, retry, or baton-dispatch implementation was made.

## Tests added

\`tests/test_s1_wp1_workspace_authority.py\` covers:

1. valid workspace and sentinel survive manager reinitialization;
2. dirty tracked and untracked workspace state survives normal initialization;
3. destructive reset changes state only with explicit opt-in;
4. unknown workspace state raises without cleanup;
5. missing authority prevents a file side effect;
6. valid authority executes and is inspectable in the tool audit.

Existing gateway and Chamber C fixtures now supply the required authority contract.

## Tests executed

- \`python -m unittest tests.test_s1_wp1_workspace_authority tests.test_tool_gateway_enforcement\` — **6 passed**
- \`python -m unittest discover -s tests -p "test_*.py" -v\` — **42 passed, 0 failed**
- \`python -m appshak_substrate.chambers.chamber_a_durability\` — **PASS**
- \`python -m appshak_substrate.chambers.chamber_b_isolation\` — **PASS**
- \`python -m appshak_substrate.chambers.chamber_c_tool_enforcement\` — **PASS**

The generated \`appshak_state\` Chamber A database is ignored runtime output. No tracked runtime state was changed.

## Known limitations

- \`authority_id\` is now required, checked for completeness/binding, and durably recorded in tool audit; it is not yet resolved against a dedicated approval/task authority store. That belongs to later task-contract work.
- Tool side effects, idempotency reservation, result recording, reply publication, and event acknowledgment remain separate operations. Crash recovery and lease renewal are S1-WP2.
- Existing command allowlists and subprocess execution are not an OS sandbox. Broader command semantics remain an architectural limitation.
- \`authorized_by\` remains a compatibility policy input; this package does not replace it with governance decision lookup.
- Invalid workspace state fails safely in place; no quarantine relocation is performed.
- The UI and model/provider paths are unchanged.

## Dependencies for S1-WP2

S1-WP2 can build on the preserved workspace contract and the authority fields carried into audit payloads. It must add attempt lifecycle, lease renewal/fencing, timeout/child-process handling, and crash reconciliation without reintroducing implicit workspace cleanup or accepting an authority display label as proof.

## Handoff

Recommended next capability: **RUNTIME_STABILIZATION**  
Recommended next work package: **S1-WP2 — Make execution attempts recoverable**

Implementation changes are present and uncommitted for review. No push was performed.

