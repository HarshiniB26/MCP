from datetime import date

from equipment.errors import EquipmentError
from equipment.text import normalize_id, normalize_space

_queue = []


def reset_review_queue():
    _queue.clear()


def review_queue():
    return list(_queue)


def _text(value, field):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def flag_for_human_review(employee_id, request, reason):
    """Append one review record. Does not approve or deny."""
    stored_reason = normalize_space(_text(reason, "reason"))
    if not stored_reason:
        raise EquipmentError("reason is required")
    record = {
        "escalation_id": f"ESC-{len(_queue) + 1:03d}",
        "employee_id": normalize_id(_text(employee_id, "employee_id")),
        "request": normalize_space(_text(request, "request")),
        "reason": stored_reason,
        "recorded_on": date.today().isoformat(),
    }
    _queue.append(record)
    return record
