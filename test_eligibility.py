from eligibility import check_request_eligibility


def test_under_the_max_is_eligible():
    result = check_request_eligibility("E1003", "monitor", as_of="2026-10-02")

    assert result["found_employee"] is True
    assert result["role"] == "standard"
    assert result["count"] == 0
    assert result["max_on_file"] == 1
    assert result["outcome"] == "eligible"
    assert result["undetermined_code"] is None
    assert result["anniversary"] is None


def test_item_spacing_is_ignored():
    result = check_request_eligibility("E1003", " Monitor ", as_of="2026-10-02")

    assert result["item"] == "monitor"
    assert result["outcome"] == "eligible"


def test_laptop_still_inside_the_wait_is_ineligible():
    result = check_request_eligibility("E1003", "laptop", as_of="2026-10-02")

    assert result["count"] == 1
    assert result["oldest_issued_on"] == "2024-05-01"
    assert result["anniversary"] == "2028-05-01"
    assert result["outcome"] == "ineligible"


def test_day_before_anniversary_is_ineligible():
    result = check_request_eligibility("E1001", "laptop", as_of="2025-01-14")

    assert result["anniversary"] == "2025-01-15"
    assert result["outcome"] == "ineligible"


def test_anniversary_day_is_eligible():
    result = check_request_eligibility("E1001", "laptop", as_of="2025-01-15")

    assert result["anniversary"] == "2025-01-15"
    assert result["outcome"] == "eligible"


def test_leap_day_moves_to_february_28_in_a_non_leap_year():
    before = check_request_eligibility("E1005", "headset", as_of="2026-02-27")
    on_day = check_request_eligibility("E1005", "headset", as_of="2026-02-28")

    assert before["anniversary"] == "2026-02-28"
    assert before["outcome"] == "ineligible"
    assert on_day["outcome"] == "eligible"


def test_leap_day_stays_february_29_in_a_leap_year():
    before = check_request_eligibility("E1005", "laptop", as_of="2028-02-28")
    on_day = check_request_eligibility("E1005", "laptop", as_of="2028-02-29")

    assert before["anniversary"] == "2028-02-29"
    assert before["outcome"] == "ineligible"
    assert on_day["outcome"] == "eligible"


def test_oldest_monitor_is_the_one_that_counts():
    result = check_request_eligibility("E1002", "monitor", as_of="2026-10-02")

    assert result["count"] == 2
    assert result["max_on_file"] == 2
    assert result["oldest_issued_on"] == "2024-01-10"
    assert result["anniversary"] == "2026-01-10"
    assert result["outcome"] == "eligible"


def test_missing_issue_date_is_undetermined():
    result = check_request_eligibility("E1004", "laptop", as_of="2026-10-02")

    assert result["outcome"] == "undetermined"
    assert result["undetermined_code"] == "missing_issue_date"


def test_issue_date_after_as_of_is_undetermined():
    result = check_request_eligibility("E1003", "laptop", as_of="2024-04-30")

    assert result["oldest_issued_on"] == "2024-05-01"
    assert result["outcome"] == "undetermined"
    assert result["undetermined_code"] == "invalid_issue_date"


def test_unknown_employee():
    result = check_request_eligibility("E9999", "headset", as_of="2026-10-02")

    assert result["found_employee"] is False
    assert result["outcome"] == "undetermined"
    assert result["undetermined_code"] == "unknown_employee"


def test_blank_employee_id():
    result = check_request_eligibility("   ", "laptop", as_of="2026-10-02")

    assert result["employee_id"] == ""
    assert result["undetermined_code"] == "unknown_employee"


def test_item_outside_the_catalog():
    result = check_request_eligibility("E1003", "standing desk", as_of="2026-10-02")

    assert result["item"] == "standing desk"
    assert result["outcome"] == "undetermined"
    assert result["undetermined_code"] == "item_not_in_catalog"
