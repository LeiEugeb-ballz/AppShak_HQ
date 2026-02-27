# explorer.py

import json
from ollama_client import generate

SYSTEM_PROMPT = """
You are HALO_EXPLORER.

Generate structured proposals in STRICT JSON.
No commentary outside JSON.

Schema:
{
  "problem": "...",
  "approach": "...",
  "confidence": 0.0-1.0
}
"""

def propose(task: str) -> dict:
    raw = generate(prompt=task, system=SYSTEM_PROMPT)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"Explorer returned malformed JSON:\n{raw}")