# critic.py

import json
from ollama_client import generate

SYSTEM_PROMPT = """
You are HALO_CRITIC.

Evaluate proposal quality.

Respond STRICTLY in JSON.

Schema:
{
  "approved": true or false,
  "reason": "...",
  "improvement_request": "..."
}
"""

def review(proposal: dict) -> dict:
    raw = generate(
        prompt=f"Evaluate this proposal:\n{json.dumps(proposal, indent=2)}",
        system=SYSTEM_PROMPT,
        temperature=0.2
    )

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"Critic returned malformed JSON:\n{raw}")