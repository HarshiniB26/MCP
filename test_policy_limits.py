from policy_limits import get_policy_limits


def test_standard_role_gets_three_limits():
    result = get_policy_limits("standard")

    assert result["found"] is True
    assert result["role"] == "standard"
    assert result["limits"] == [
        {"item": "laptop", "max_on_file": 1, "wait_years": 4},
        {"item": "monitor", "max_on_file": 1, "wait_years": 3},
        {"item": "headset", "max_on_file": 1, "wait_years": 2},
    ]


def test_manager_role_gets_three_limits():
    result = get_policy_limits("manager")

    assert result["found"] is True
    assert result["role"] == "manager"
    assert result["limits"] == [
        {"item": "laptop", "max_on_file": 1, "wait_years": 2},
        {"item": "monitor", "max_on_file": 2, "wait_years": 2},
        {"item": "headset", "max_on_file": 1, "wait_years": 1},
    ]


def test_role_ignores_capitals_and_spaces():
    result = get_policy_limits(" Manager ")

    assert result["found"] is True
    assert result["role"] == "manager"


def test_unknown_role_is_not_found():
    result = get_policy_limits("intern")

    assert result["found"] is False
    assert result["role"] == "intern"
    assert "limits" not in result


def test_blank_role_is_not_found():
    result = get_policy_limits("   ")

    assert result["found"] is False
    assert result["role"] == ""
