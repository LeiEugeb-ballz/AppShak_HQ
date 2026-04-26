import copy
import json

# --- HOOKS (must exist in your system) ---
from kernel import run_cycle_once   # single-cycle execution
from memory import MemoryStore      # your memory system


def snapshot_state(state):
    """Create a minimal comparable snapshot"""
    return {
        "task_queue": copy.deepcopy(state.get("task_queue")),
        "last_decision": state.get("last_decision"),
        "selected_action": state.get("selected_action"),
        "agent_states": copy.deepcopy(state.get("agent_states")),
    }


def run_with_memory(enabled: bool):
    # fresh system state
    memory = MemoryStore()
    state = {
        "cycle": 0,
        "task_queue": [],
        "last_decision": None,
        "selected_action": None,
        "agent_states": {},
    }

    # seed memory with a known failure pattern
    if enabled:
        memory.store({
            "task": "example_task",
            "action": "approach_A",
            "outcome": "failure",
            "lessons": ["approach_A fails due to timeout"],
            "timestamp": 1
        })

    # run a few deterministic cycles
    for _ in range(3):
        run_cycle_once(state, memory)

    return snapshot_state(state)


def main():
    print("Running Phase 2 validation...")

    no_mem = run_with_memory(enabled=False)
    with_mem = run_with_memory(enabled=True)

    print("\n--- RESULT COMPARISON ---")
    print("NO MEMORY:", json.dumps(no_mem, indent=2))
    print("WITH MEMORY:", json.dumps(with_mem, indent=2))

    if no_mem == with_mem:
        print("\n❌ FAIL: Memory does NOT change behavior")
    else:
        print("\n✅ PASS: Memory alters system decisions")

    # stricter assertion
    assert no_mem != with_mem, "Memory is not influencing decisions"


if __name__ == "__main__":
    main()