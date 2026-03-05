# Evidence Index - Current Test State

## Run Metadata

- Run label: $runId
- Date: 2026-03-05
- Branch: main
- Commit: $(git rev-parse --short HEAD)
- Ports used: N/A (runtime services not launched in this run)

## Tested (Executed Now)

1. Test command(s) actually run:
   - python -m unittest discover -s tests -p "test_*.py" -v
2. Runtime checks actually run:
   - None
3. Gate(s) completed:
   - Automated unittest gate

## Deferred (Could Be Tested)

1. Deferred command(s):
   - Runtime stack launch commands
   - python -m appshak_stability.run --duration-hours 6
2. Deferred runtime gate(s):
   - 6-hour stability gate
   - replay/hash continuity gate
3. Deferral reason:
   - Development-flow feedback run, not production certification run

## Automated Test Evidence

1. Full suite stdout/stderr:
   - docs/certification/results/run_20260305T162154Z/unittest_full.log

## Notes / Deviations

1. Deviation:
   - Runtime and burn gates deferred.
2. Impact:
   - Not a production certification decision.
3. Follow-up action:
   - Run strict certification block at phase freeze.
