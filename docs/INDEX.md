# AppShak HQ Documentation Index

This is the canonical navigator for repository documentation. It classifies
material by engineering role so active guidance is discoverable without
discarding certification, research, prototype, or runtime history.

Start with [README.md](../README.md), then read
[CURRENT_STATUS.md](../CURRENT_STATUS.md).

## Navigation by need

| If you need to… | Read |
|---|---|
| Understand the system and run the main stack | [README.md](../README.md) |
| Install a machine | [Environment Setup](../ENVIRONMENT_SETUP.md) and [Dependency Guidance](DEPENDENCIES.md) |
| Understand maturity and certification records | [Current Status](../CURRENT_STATUS.md) |
| Learn the architecture and engineering boundaries | [Developer Onboarding](../ONBOARDING.md) |
| Contribute or verify changes | [Contributing Guide](../CONTRIBUTING.md) |
| Run or understand a subsystem | [Active runtime and subsystem documents](#active-runtime-and-subsystem-documents) |
| Review certification scope and evidence | [Certification](#certification) |
| Inspect history, drafts, research, or prototypes | [Historical archival and draft material](#historical-archival-and-draft-material) |

## ACTIVE

These are the primary documents for a current engineer.

- [Repository Overview and Runtime Guide](../README.md)
- [Current Status](../CURRENT_STATUS.md)
- [Environment Setup](../ENVIRONMENT_SETUP.md)
- [Dependency Guidance](DEPENDENCIES.md)
- [Developer Onboarding](../ONBOARDING.md)
- [Contributing Guide](../CONTRIBUTING.md)

## SUPPORTING

### Active runtime and subsystem documents

- [Substrate Guide](../appshak_substrate/README.md) — durable event store,
  supervision, worktrees, chambers, and test commands.
- [Substrate Bug-Fix Notes](../appshak_substrate/BUGFIX_NOTES.md) — documented
  Windows CRLF/worktree incident and its audit record.
- [Observability UI Guide](../appshak-ui/README.md) — UI endpoints, views, and
  local development commands.
- [Phase 3.4 Projection Semantic Enrichment](phase_3_4_projection_semantic_enrichment.md)
  — worker and derived projection contract.
- [Phase 3 Governance Completion Record](phase_3_governance_complete.md) —
  registry, relationship, arbitration, ledger, and replay record.
- [Phase 4 Integrity and Self-Observation](phase_4_integrity_self_observation.md)
  — integrity and self-observation design record.
- [Codex Bootstrap](CODEX_BOOTSTRAP.md) — external engineering-agent guardrails;
  this is supporting guidance, not an AppShak runtime dependency.

## CERTIFICATION

### Planning pack

- [Certification Planning Pack](certification/README.md)
- [00 — Certification Scope](certification/00_certification_scope.md)
- [01 — Repository Test Inventory](certification/01_repo_test_inventory.md)
- [02 — Master Validation Plan](certification/02_master_validation_plan.md)
- [03 — Execution Checklists](certification/03_execution_checklists.md)
- [04 — Evidence Index Template](certification/04_evidence_index_template.md)
- [05 — Signoff Template](certification/05_signoff_template.md)
- [06 — Module Certificate Template](certification/06_module_certificate_template.md)

### Phase and run records

- [Phase 2 Substrate Signoff](phase_2_substrate_signoff.md)
- [Phase 4 Operational Validation — Partial Run](phase_4_operational_validation.md)
- [Phase 4 Evaluation Summary](phase4/PHASE4_EVAL_SUMMARY.md)
- [2026-03-05 Current Test-State Evidence Index](certification/results/run_20260305T162154Z/EVIDENCE_INDEX.md)
- [2026-03-05 Current Test-State Certificate](certification/results/run_20260305T162154Z/FINAL_CURRENT_TEST_STATE_CERTIFICATE.md)
- [2026-03-05 Module Test-State Snapshot](certification/results/run_20260305T162154Z/MODULE_TEST_STATE_SNAPSHOT.md)
- [2026-03-05 One-Hour Run Evidence Index](certification/results/run_20260305T174718Z/EVIDENCE_INDEX.md)
- [2026-03-05 One-Hour Stability Feedback](certification/results/run_20260305T174718Z/ONE_HOUR_STABILITY_FEEDBACK_REPORT.md)

### Raw Phase 2 evidence

- [Evidence directory](evidence/phase_2/) containing chamber output,
  crash-recovery, idempotency, plugin-boundary, supervisor, swarm, unit-test,
  and worker-log captures.

## HISTORICAL

These documents preserve prior engineering decisions and completed phase
records. They remain valuable context but are not the primary setup path.

- [Research and early-system overview](../Research%2C%20docs%20and%20work/README.md)
- [Sprint Roadmap](../Research%2C%20docs%20and%20work/SPRINT_ROADMAP.md)
- [Developer Stack Handover](../Research%2C%20docs%20and%20work/DeveloperStack1.txt)
- [Planning Notes](../Research%2C%20docs%20and%20work/Notes_260216_221430.txt)
- [GUI Notes](../Research%2C%20docs%20and%20work/GUI.txt)
- [Constitution and Roadmap PDF](../Research%2C%20docs%20and%20work/AI%20Organization%20Constitution%20%26%20Roadmap.pdf)
- [Final Constitution PDF](../Research%2C%20docs%20and%20work/AppShak%20Organization%20Constitution%20-%20Final.pdf)
- `Research, docs and work/AppShak-Compile.txt` — empty tracked text file.
- `Research, docs and work/gemini-3-developer-codex-ultimate-850-prompts-edition.PDF`
- `Research, docs and work/Multi-Agent Systems_ Sources and Takeaways.docx`
- `Research, docs and work/Visualizing-Multi-Agent-Systems.pdf`

## ARCHIVAL

These materials are preserved implementation or evidence history. They are not
the normal source of runtime instructions.

- `run_archives/` — failed Phase 3B attempts and pre-burn-in state snapshots,
  each with preserved run context.
- `stashed_instances_2026-02-19/` — prior `appshak_live`, `appshak_office`, and
  `Halo` implementations, including their local documentation.
- `appshak-hq-repo/appshak-hq-dashboard/` — nested dashboard prototype with
  [README](../appshak-hq-repo/appshak-hq-dashboard/README.md) and
  [architecture](../appshak-hq-repo/appshak-hq-dashboard/docs/ARCHITECTURE.md).
- `untraacked_20260503/` — preserved Phase 4 state, validation samples,
  stability metadata, and timestamped integrity reports.

## DRAFT

- `Drafts/AppShakDrafts.pdf`
- `Drafts/CONSTITUTIONAL INVARIANTS - review and test - v0.01.pdf`
- `Drafts/The AppShak vNext Specification.txt`

These documents preserve early constitutional and architecture context. They
are not rewritten or replaced by this index.

## Documentation graph

```text
README.md
├── CURRENT_STATUS.md
├── ENVIRONMENT_SETUP.md
│   └── docs/DEPENDENCIES.md
├── ONBOARDING.md
│   └── CONTRIBUTING.md
├── subsystem guides
│   ├── appshak_substrate/README.md
│   └── appshak-ui/README.md
└── docs/INDEX.md
    ├── certification planning and evidence
    ├── phase records
    ├── historical research
    ├── archival implementations and generated evidence
    └── drafts
```
