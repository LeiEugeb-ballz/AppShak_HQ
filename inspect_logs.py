import json
from collections import defaultdict

LOG_FILE = "run.log"  # adjust if needed


def load_logs():
    with open(LOG_FILE, "r") as f:
        return [json.loads(line) for line in f if line.strip()]


def analyze(logs):
    stats = defaultdict(int)

    for entry in logs:
        if entry.get("event") == "memory_retrieved":
            stats["memory_calls"] += 1

        if entry.get("event") == "decision":
            if "memory_factor" in entry:
                stats["memory_used_in_scoring"] += 1

            if entry.get("memory_influenced"):
                stats["memory_changed_decision"] += 1

        if entry.get("event") == "proposal_rejected":
            if entry.get("reason") == "memory_failure_pattern":
                stats["memory_filtering"] += 1

    return stats


def report(stats):
    print("\n--- LOG ANALYSIS ---")

    print(f"Memory retrieval calls:        {stats['memory_calls']}")
    print(f"Used in scoring:              {stats['memory_used_in_scoring']}")
    print(f"Changed decisions:            {stats['memory_changed_decision']}")
    print(f"Filtered by memory:           {stats['memory_filtering']}")

    if stats["memory_used_in_scoring"] == 0:
        print("\n❌ FAIL: Memory not used in scoring")

    if stats["memory_changed_decision"] == 0:
        print("\n❌ FAIL: Memory not changing decisions")

    if stats["memory_filtering"] == 0:
        print("\n⚠️ WARNING: No memory-based filtering detected")

    if (
        stats["memory_used_in_scoring"] > 0 and
        stats["memory_changed_decision"] > 0
    ):
        print("\n✅ PASS: Memory is actively influencing behavior")


def main():
    logs = load_logs()
    stats = analyze(logs)
    report(stats)


if __name__ == "__main__":
    main()