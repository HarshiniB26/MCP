from employee_info import get_employee_info


def test_known_employee_role():
    result = get_employee_info("E1001", as_of="2026-10-02")
    assert result["found"] is True
    assert result["role"] == "standard"
    assert result["name"] == "Priya Shah"


def test_id_match_ignores_case():
    result = get_employee_info("e1003", as_of="2026-10-02")
    assert result["found"] is True
    assert result["employee_id"] == "E1003"


def test_unknown_employee():
    result = get_employee_info("E9999", as_of="2026-10-02")
    assert result["found"] is False
    assert result["employee_id"] == "E9999"


def test_blank_employee_id():
    result = get_employee_info("   ", as_of="2026-10-02")
    assert result["found"] is False
    assert result["employee_id"] == ""


def test_missing_issue_date_is_preserved():
    result = get_employee_info("E1004", as_of="2026-10-02")
    laptop = next(item for item in result["equipment"] if item["item"] == "laptop")
    assert laptop["issued_on"] is None


def test_tenure_uses_the_passed_date():
    result = get_employee_info("E1001", as_of="2026-10-02")
    assert result["tenure_years"] == 6
    assert result["as_of"] == "2026-10-02"
