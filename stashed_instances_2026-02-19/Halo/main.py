# main.py

from explorer import propose
from critic import review

MAX_REFINEMENTS = 2

def run():
    task = "Identify a small automation opportunity for a local small business."

    print("\n--- HALO START ---\n")

    refinements = 0

    while refinements <= MAX_REFINEMENTS:
        print(f"\nExplorer attempt {refinements + 1}")

        proposal = propose(task)
        print("Proposal:", proposal)

        verdict = review(proposal)
        print("Critic:", verdict)

        if verdict.get("approved"):
            print("\nFINAL APPROVED PROPOSAL")
            print(proposal)
            break

        refinements += 1

        if refinements > MAX_REFINEMENTS:
            print("\nFAILED AFTER MAX REFINEMENTS")
            break

        task = f"""
Previous proposal was rejected.
Reason: {verdict.get("reason")}
Improvement requested: {verdict.get("improvement_request")}

Please generate improved version.
"""

    print("\n--- HALO END ---\n")


if __name__ == "__main__":
    run()