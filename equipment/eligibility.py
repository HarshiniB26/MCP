from equipment.employee_info import _anniversary, _as_of_date, completed_years, get_employee_info
from equipment.errors import DirectoryError
from equipment.policy_limits import get_policy_limits
from equipment.reasons import CATALOG
from equipment.text import normalize_text


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
    normalized_item = normalize_text(item)
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

    policy = get_policy_limits(info["role"])
    if not policy.get("found"):
        raise DirectoryError(f"No policy limits for role {info['role']!r}")
    limits = policy["limits"]
    limit = next((row for row in limits if row["item"] == normalized_item), None)
    if limit is None:
        raise DirectoryError(f"No limit for {normalized_item!r} on role {info['role']!r}")
    matches = [row for row in info["equipment"] if row["item"] == normalized_item]
    result["count"] = len(matches)
    result["max_on_file"] = limit["max_on_file"]
    result["wait_years"] = limit["wait_years"]

    if len(matches) < limit["max_on_file"]:
        result["outcome"] = "eligible"
        return result

    if len(matches) > limit["max_on_file"]:
        result["outcome"] = "ineligible"
        return result

    if any(row.get("issued_on") is None for row in matches):
        result["undetermined_code"] = "missing_issue_date"
        return result

    issued = sorted(row["issued_on"] for row in matches)
    try:
        oldest = _as_of_date(issued[0])
    except ValueError as error:
        raise DirectoryError(f"Issue date {issued[0]!r} is not YYYY-MM-DD") from error
    result["oldest_issued_on"] = oldest.isoformat()

    try:
        future = any(_as_of_date(day) > on for day in issued)
    except ValueError as error:
        raise DirectoryError("An issue date is not YYYY-MM-DD") from error
    if future:
        result["undetermined_code"] = "invalid_issue_date"
        return result

    anniversary = _anniversary(oldest, limit["wait_years"])
    result["anniversary"] = anniversary.isoformat()
    result["completed_years"] = completed_years(oldest, on)
    result["outcome"] = "eligible" if on >= anniversary else "ineligible"
    return result
