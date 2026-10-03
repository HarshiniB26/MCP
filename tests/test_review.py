from datetime import date

import pytest

from equipment.errors import EquipmentError
from equipment.review import flag_for_human_review, reset_review_queue, review_queue


def setup_function():
    reset_review_queue()


def test_first_record_is_esc_001():
    record = flag_for_human_review(
        "E1003",
        "I need a monitor because my doctor said I need it for neck pain.",
        "Reason asks for shared, third-party, or accommodation use, which these limits do not decide.",
    )

    assert record["escalation_id"] == "ESC-001"
    assert record["employee_id"] == "E1003"
    assert record["recorded_on"] == date.today().isoformat()
    assert review_queue() == [record]


def test_second_call_keeps_the_first_record():
    first = flag_for_human_review(
        "E1002",
        "I need a third monitor.",
        "Policy allows replacing the oldest item, but the reason asks for an extra unit.",
    )
    second = flag_for_human_review(
        "E9999",
        "Could I get a headset please?",
        "Employee id is not in the directory, so role and equipment cannot be checked.",
    )

    assert first["escalation_id"] == "ESC-001"
    assert second["escalation_id"] == "ESC-002"
    assert review_queue() == [first, second]


def test_employee_id_ignores_case_and_spaces():
    record = flag_for_human_review(
        " e1004 ", "Replace my laptop.", "Issue date is missing, so the wait period cannot be checked."
    )

    assert record["employee_id"] == "E1004"


def test_a_blank_reason_is_rejected():
    with pytest.raises(EquipmentError):
        flag_for_human_review("E1001", "I need a laptop.", "   ")

    assert review_queue() == []


def test_blank_employee_id_is_stored_empty():
    record = flag_for_human_review(
        "   ", "I need a laptop.", "Employee id is not in the directory, so role and equipment cannot be checked."
    )

    assert record["employee_id"] == ""
    assert record["escalation_id"] == "ESC-001"
