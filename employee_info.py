import json
from datetime import date
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "employees.json"


def _as_of_date(as_of):
    if as_of is None:
        return date.today()
    if isinstance(as_of, date):
        return as_of
    return date.fromisoformat(as_of)


def _anniversary(start, years):
    try:
        return date(start.year + years, start.month, start.day)
    except ValueError:
        return date(start.year + years, start.month, 28)


def completed_years(start, as_of):
    years = as_of.year - start.year
    if years > 0 and as_of < _anniversary(start, years):
        years -= 1
    return max(years, 0)


def get_employee_info(employee_id, as_of=None):
    """Look up role, tenure, and equipment. as_of defaults to today's date."""
    on = _as_of_date(as_of)
    normalized = (employee_id or "").strip().upper()
    if not normalized:
        return {"found": False, "employee_id": "", "as_of": on.isoformat()}

    employees = json.loads(DATA_FILE.read_text())
    for employee in employees:
        if employee["employee_id"].upper() == normalized:
            hired = date.fromisoformat(employee["hired_on"])
            return {
                "found": True,
                "employee_id": employee["employee_id"],
                "name": employee["name"],
                "role": employee["role"],
                "hired_on": employee["hired_on"],
                "tenure_years": completed_years(hired, on),
                "equipment": employee["equipment"],
                "as_of": on.isoformat(),
            }
    return {"found": False, "employee_id": normalized, "as_of": on.isoformat()}
