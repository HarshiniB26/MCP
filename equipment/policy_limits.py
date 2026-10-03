from pathlib import Path

from equipment.errors import DirectoryError
from equipment.storage import read_json

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "policy.json"


def get_policy_limits(role):
    """Return the entitlement rows for a role."""
    normalized = (role or "").strip().lower()
    if not normalized:
        return {"found": False, "role": ""}

    rows = read_json(DATA_FILE)
    if not isinstance(rows, list):
        raise DirectoryError("Policy file must be a list of limits.")
    try:
        limits = [
            {
                "item": row["item"],
                "max_on_file": row["max_on_file"],
                "wait_years": row["wait_years"],
            }
            for row in rows
            if row["role"] == normalized
        ]
    except (KeyError, TypeError) as error:
        raise DirectoryError("Policy file has a row missing role, item, max_on_file, or wait_years") from error
    if not limits:
        return {"found": False, "role": normalized}
    return {"found": True, "role": normalized, "limits": limits}
