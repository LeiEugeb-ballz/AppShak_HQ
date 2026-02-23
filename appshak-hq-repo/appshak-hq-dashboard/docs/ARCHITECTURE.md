# AppShak Cognitive Organism — Architecture

## The Four Constitutional Frameworks

### 1. Directive Framework (Chief Veto)
Chief holds absolute veto over any proposal. No build proceeds without Chief sign-off,
and no build deploys without Boss approval (when toggle is ON).

### 2. Biotic Framework (P2P Advice)
Agents share skills and strategies at the Water Cooler. Knowledge propagates peer-to-peer,
not top-down. Every session is logged with timestamps.

### 3. Protocol Framework (Token Voting)
Proposals are scored by viability, TAM, and confidence. Only proposals above threshold
reach the boardroom. Chief arbitrates with a weighted vote.

## Five North Star Metrics

| Metric | Target |
|---|---|
| Competence Expansion | Skills per cycle trending up |
| Autonomous Discovery | >80% of proposals self-initiated |
| Token/Value Ratio | >0.80 |
| Trust Stability | Inter-agent trust score >0.7 |
| Systemic Resilience | 24-hour crash-free run |

## The Closed Loop

```
┌─────────────────────────────────────────────────┐
│                                                 │
│  SCOUT ──► BOARDROOM ──► BUILDER ──► QA        │
│    ▲                              │             │
│    │                              ▼             │
│  MEMORY ◄──── UPDATE ◄── WATER COOLER          │
│                                                 │
└─────────────────────────────────────────────────┘
```

## Reality Gap (Current vs Target)

| Layer | Current (Prototype) | Target (Production) |
|---|---|---|
| Isolation | In-memory simulation | Git worktrees per agent |
| Persistence | Session only | SQLite WAL |
| Process Control | setInterval | tmux + Claude Code Hooks |
| Safety | Constitutional checks | Safeguards.py enforcement |
| Comms | Direct function calls | 100% EventBus routing |

## Test Chambers

- **Chamber A** — Config Integrity: escalation, buffer, sprint
- **Chamber B** — Integration Harness: spawn, liveness, cleanup  
- **Chamber C** — Policy Sandbox: governance and safeguards
- **Chamber F** — Operator Drill: pause, cancel, quarantine
- **Chamber G** — Benchmark Track: success rate, time-to-merge
