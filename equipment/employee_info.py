import calendar
from datetime import date
from pathlib import Path

from equipment.errors import DirectoryError
from equipment.storage import read_json
from equipment.text import normalize_id, normalize_text

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "employees.json"


def _as_of_date(as_of):
    if as_of is None:
        return date.today()
    if isinstance(as_of, date):
        return as_of
    if not isinstance(as_of, str):
        raise ValueError(f"as_of must be a date or YYYY-MM-DD string, got {type(as_of).__name__}")
    try:
        return date.fromisoformat(as_of)
    except ValueError as error:
        raise ValueError(f"as_of must be YYYY-MM-DD, got {as_of!r}") from error


def _anniversary(start, years):
    """Same month and day, or the last day of that month when the day does not exist."""
    year = start.year + years
    last_day = calendar.monthrange(year, start.month)[1]
    return date(year, start.month, min(start.day, last_day))


def completed_years(start, as_of):
    years = as_of.year - start.year
    if years > 0 and as_of < _anniversary(start, years):
        years -= 1
    return max(years, 0)


def get_employee_info(employee_id, as_of=None):
    """Look up role, tenure, and equipment. as_of defaults to today's date."""
    on = _as_of_date(as_of)
    normalized = normalize_id(employee_id)
    if not normalized:
        return {"found": False, "employee_id": "", "as_of": on.isoformat()}

    employees = read_json(DATA_FILE)
    if not isinstance(employees, list):
        raise DirectoryError("Employee directory must be a list of records.")
    for employee in employees:
        if not isinstance(employee, dict):
            raise DirectoryError("Employee directory has a record that is not an object.")
        try:
            record_id = employee["employee_id"]
        except KeyError as error:
            raise DirectoryError("Employee record is missing employee_id") from error
        if normalize_id(record_id) == normalized:
            try:
                hired = date.fromisoformat(employee["hired_on"])
                equipment = employee["equipment"]
                if not isinstance(equipment, list):
                    raise DirectoryError(f"Equipment for {record_id} must be a list")
                return {
                    "found": True,
                    "employee_id": normalized,
                    "name": employee["name"],
                    "role": normalize_text(employee["role"]),
                    "hired_on": employee["hired_on"],
                    "tenure_years": completed_years(hired, on),
                    "equipment": _equipment_rows(record_id, equipment),
                    "as_of": on.isoformat(),
                }
            except DirectoryError:
                raise
            except (KeyError, TypeError, ValueError) as error:
                raise DirectoryError(
                    f"Employee record {record_id} is incomplete or has a bad hire date"
                ) from error
    return {"found": False, "employee_id": normalized, "as_of": on.isoformat()}


def _equipment_rows(record_id, equipment):
    rows = []
    for row in equipment:
        if not isinstance(row, dict):
            raise DirectoryError(f"Equipment for {record_id} has a row that is not an object")
        try:
            rows.append(
                {
                    "item": normalize_text(row["item"]),
                    "issued_on": row["issued_on"],
                }
            )
        except KeyError as error:
            raise DirectoryError(
                f"Equipment for {record_id} is missing item or issued_on"
            ) from error
    return rows
