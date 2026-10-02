import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "policy.json"


def get_policy_limits(role):
    """Return the entitlement rows for a role. This is not an MCP tool."""
    normalized = (role or "").strip().lower()
    if not normalized:
        return {"found": False, "role": ""}

    rows = json.loads(DATA_FILE.read_text())
    limits = [
        {
            "item": row["item"],
            "max_on_file": row["max_on_file"],
            "wait_years": row["wait_years"],
        }
        for row in rows
        if row["role"] == normalized
    ]
    if not limits:
        return {"found": False, "role": normalized}
    return {"found": True, "role": normalized, "limits": limits}
