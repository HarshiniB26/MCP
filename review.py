from datetime import date

_queue = []


def reset_review_queue():
    _queue.clear()


def review_queue():
    return list(_queue)


def flag_for_human_review(employee_id, request, reason):
    """Append one review record. Does not approve or deny."""
    normalized = (employee_id or "").strip().upper()
    record = {
        "escalation_id": f"ESC-{len(_queue) + 1:03d}",
        "employee_id": normalized,
        "request": request,
        "reason": reason,
        "recorded_on": date.today().isoformat(),
    }
    _queue.append(record)
    return record
