import re

from employee_info import _anniversary, _as_of_date, completed_years, get_employee_info
from policy_limits import get_policy_limits

CATALOG = {"laptop", "monitor", "headset"}


def _normalize_item(item):
    return re.sub(r"\s+", " ", (item or "").strip().lower())


def _result(employee_id, item, as_of, found, role):
    return {
        "employee_id": employee_id,
        "item": item,
        "as_of": as_of,
        "found_employee": found,
        "role": role,
        "outcome": "undetermined",
        "undetermined_code": None,
        "count": None,
        "max_on_file": None,
        "wait_years": None,
        "oldest_issued_on": None,
        "anniversary": None,
        "completed_years": None,
    }


def check_request_eligibility(employee_id, item, as_of=None):
    """Numeric entitlement only. Does not read the employee's reason."""
    on = _as_of_date(as_of)
    info = get_employee_info(employee_id, as_of=on)
    normalized_item = _normalize_item(item)
    result = _result(
        info["employee_id"],
        normalized_item,
        on.isoformat(),
        info["found"],
        info.get("role"),
    )

    if not info["found"]:
        result["role"] = None
        result["undetermined_code"] = "unknown_employee"
        return result

    if normalized_item not in CATALOG:
        result["undetermined_code"] = "item_not_in_catalog"
        return result

    limits = get_policy_limits(info["role"])["limits"]
    limit = next(row for row in limits if row["item"] == normalized_item)
    matches = [row for row in info["equipment"] if row["item"] == normalized_item]
    result["count"] = len(matches)
    result["max_on_file"] = limit["max_on_file"]
    result["wait_years"] = limit["wait_years"]

    if len(matches) < limit["max_on_file"]:
        result["outcome"] = "eligible"
        return result

    if any(row["issued_on"] is None for row in matches):
        result["undetermined_code"] = "missing_issue_date"
        return result

    issued = sorted(row["issued_on"] for row in matches)
    oldest = _as_of_date(issued[0])
    result["oldest_issued_on"] = oldest.isoformat()

    if any(_as_of_date(day) > on for day in issued):
        result["undetermined_code"] = "invalid_issue_date"
        return result

    anniversary = _anniversary(oldest, limit["wait_years"])
    result["anniversary"] = anniversary.isoformat()
    result["completed_years"] = completed_years(oldest, on)
    result["outcome"] = "eligible" if on >= anniversary else "ineligible"
    return result
