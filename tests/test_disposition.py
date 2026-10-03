"""Decisions the data settles, the limits on the model's judgement, and the recorded outcome.

Dates are passed in so the results do not depend on the day the suite runs.
"""

from equipment.disposition import (
    Investigation,
    named_items,
    must_include,
    needs_reflection,
    outcome,
    rule_line,
    unconfirmed_reply,
)
from equipment.eligibility import check_request_eligibility
from equipment.employee_info import get_employee_info
from equipment.policy_limits import get_policy_limits
from equipment.reasons import REPLY_NOT_CONFIRMED, reason_instructions
from equipment.review import flag_for_human_review, reset_review_queue

AS_OF = "2026-10-02"


def setup_function():
    reset_review_queue()


def investigate(employee_id, request, as_of=AS_OF):
    """Make every call the data requires. No model judgement is applied."""
    investigation = Investigation(employee_id, request)
    seen = []
    while True:
        step = investigation.next_action()
        if step is None:
            break
        name, arguments = step
        seen.append(name)
        if name == "get_employee_info":
            payload = get_employee_info(arguments["employee_id"], as_of=as_of)
        elif name == "get_policy_limits":
            payload = get_policy_limits(arguments["role"])
        elif name == "check_request_eligibility":
            payload = check_request_eligibility(arguments["employee_id"], arguments["item"], as_of=as_of)
        elif name == "flag_for_human_review":
            payload = flag_for_human_review(**arguments)
        else:
            raise AssertionError(name)
        investigation.observe(name, payload, arguments)
    investigation.tool_names = seen
    return investigation


def judge(investigation, reason):
    """The model escalates because of what the employee wrote."""
    arguments = {"employee_id": investigation.employee_id, "request": investigation.request, "reason": reason}
    assert investigation.call_problem("flag_for_human_review", arguments, judging=True) is None
    investigation.observe("flag_for_human_review", flag_for_human_review(**arguments), arguments)


def test_items_follow_the_order_written_and_ignore_plurals():
    assert named_items("I need a monitor and a headset") == ["monitor", "headset"]
    assert named_items("laptop or monitor, then another monitor") == ["laptop", "monitor"]
    assert named_items("I need monitors") == ["monitor"]


def test_approve_when_count_is_under_the_max():
    investigation = investigate("E1003", "Please send me a monitor, I don't have one at my desk.")

    decision = investigation.decisions()[0]
    assert investigation.tool_names == [
        "get_employee_info",
        "get_policy_limits",
        "check_request_eligibility",
    ]
    assert decision["disposition"] == "approve"
    assert decision["reason_code"] is None
    reply = investigation.reply()
    assert reply.startswith("Approved.")
    assert "Lena Cho" in reply
    assert "count 0" in reply


def test_deny_when_the_wait_is_unfinished():
    investigation = investigate("E1001", "My monitor keeps going black, I need another monitor.")

    decision = investigation.decisions()[0]
    assert decision["disposition"] == "deny"
    assert "flag_for_human_review" not in investigation.tool_names
    reply = investigation.reply()
    assert reply.startswith("Denied.")
    assert "2028-06-01" in reply


def test_replacement_is_approved_when_the_wait_is_finished():
    investigation = investigate("E1001", "Please replace my laptop.")

    assert investigation.decisions()[0]["disposition"] == "approve"


def test_code_does_not_read_the_employees_words():
    investigation = investigate("E1003", "My wrists ache, so I need an ergonomic monitor.")

    assert investigation.decisions()[0]["disposition"] == "approve"
    assert "flag_for_human_review" not in investigation.tool_names


def test_escalate_when_the_issue_date_is_missing():
    investigation = investigate("E1004", "My laptop keeps freezing, can I have a new laptop?")

    decision = investigation.decisions()[0]
    assert decision["reason_code"] == "missing_issue_date"
    assert investigation.reviews[0]["escalation_id"] == "ESC-001"
    reply = investigation.reply()
    assert "approved" not in reply.lower()
    assert "denied" not in reply.lower()
    assert "ESC-001" in reply


def test_unknown_employee_escalates_before_any_item_check():
    investigation = investigate("E9999", "Could I get a headset please?")

    assert investigation.tool_names == ["get_employee_info", "flag_for_human_review"]
    assert investigation.decisions()[0]["reason_code"] == "unknown_employee"


def test_item_outside_the_catalog_escalates():
    investigation = investigate("E1003", "I need a standing desk.")

    assert investigation.decisions()[0]["reason_code"] == "item_not_in_catalog"


def test_one_sentence_can_deny_one_item_and_approve_another():
    investigation = investigate("E1003", "I need a laptop and a monitor.")

    dispositions = [decision["disposition"] for decision in investigation.decisions()]
    assert dispositions == ["deny", "approve"]
    assert "flag_for_human_review" not in investigation.tool_names
    reply = investigation.reply()
    assert "Denied." in reply
    assert "Approved." in reply


def test_model_can_escalate_an_item_the_data_approves():
    investigation = investigate("E1001", "Can I get a spare laptop? I'd like to keep the one I have.")
    judge(investigation, "The employee wants a second laptop while keeping the current one, not a replacement.")

    decision = investigation.decisions()[0]
    assert decision["disposition"] == "escalate"
    assert decision["reason_code"] == "model_judgement"
    assert decision["review"]["escalation_id"] == "ESC-001"
    reply = investigation.reply()
    assert reply.startswith("Escalated. Case ESC-001 for laptop.")


def test_model_can_escalate_an_item_the_data_denies():
    investigation = investigate("E1001", "My back hurts when I work, so I need a different monitor.")
    judge(investigation, "The employee describes a medical need that may justify an exception.")

    assert investigation.decisions()[0]["disposition"] == "escalate"
    assert investigation.incomplete_reason() is None


def test_model_escalation_covers_the_items_the_data_would_settle():
    investigation = investigate("E1003", "I need a laptop and a monitor for my new intern.")
    judge(investigation, "The equipment is for another person, not the employee.")

    assert [decision["disposition"] for decision in investigation.decisions()] == ["escalate", "escalate"]
    assert [review["escalation_id"] for review in investigation.reviews] == ["ESC-001"]


def test_model_escalates_after_a_required_escalation():
    investigation = investigate("E1004", "My laptop and my monitor are slow, and both are for my team.")
    judge(investigation, "The equipment is for the employee's team, not the employee.")

    decisions = investigation.decisions()
    assert [decision["reason_code"] for decision in decisions] == ["missing_issue_date", "model_judgement"]
    assert [review["escalation_id"] for review in investigation.reviews] == ["ESC-001", "ESC-002"]


def test_model_cannot_escalate_before_every_item_is_checked():
    investigation = Investigation("E1003", "I need a monitor for my intern.")
    investigation.observe("get_employee_info", get_employee_info("E1003", as_of=AS_OF))

    problem = investigation.call_problem(
        "flag_for_human_review",
        {"employee_id": "E1003", "request": "x", "reason": "The monitor is for another person."},
    )
    assert problem.startswith("Not yet.")


def test_model_cannot_escalate_twice():
    investigation = investigate("E1003", "I need a monitor for my intern.")
    judge(investigation, "The monitor is for another person.")

    problem = investigation.call_problem(
        "flag_for_human_review",
        {"employee_id": "E1003", "request": "x", "reason": "Still for another person."},
    )
    assert "already escalated as ESC-001" in problem


def test_model_cannot_add_a_judgement_when_every_item_is_already_escalated():
    investigation = investigate("E9999", "My ears hurt with my old one, so I want a softer headset.")

    problem = investigation.call_problem(
        "flag_for_human_review",
        {"employee_id": "E9999", "request": "x", "reason": "Medical need."},
    )
    assert problem == "Every item is already escalated. Write the decision."


def test_settled_items_are_escalated_only_through_the_judgement_step():
    investigation = investigate("E1001", "My monitor keeps going black, I need another monitor.")
    arguments = {"employee_id": "E1001", "request": "x", "reason": "The wait has not ended."}

    assert "do not escalate now" in investigation.call_problem("flag_for_human_review", arguments)
    assert investigation.call_problem("flag_for_human_review", arguments, judging=True) is None


def test_model_must_give_a_reason():
    investigation = investigate("E1003", "I need a monitor for my intern.")

    problem = investigation.call_problem(
        "flag_for_human_review",
        {"employee_id": "E1003", "request": "x", "reason": "  "},
    )
    assert problem.startswith("Write a one-sentence reason")


def test_a_required_escalation_must_copy_the_reason_exactly():
    investigation = Investigation("E1004", "My laptop keeps freezing, can I have a new laptop?")
    investigation.observe("get_employee_info", get_employee_info("E1004", as_of=AS_OF))
    investigation.observe("get_policy_limits", get_policy_limits("standard"))
    arguments = {"employee_id": "E1004", "item": "laptop"}
    investigation.observe(
        "check_request_eligibility", check_request_eligibility("E1004", "laptop", as_of=AS_OF), arguments
    )

    wrong = {"employee_id": "E1004", "request": "x", "reason": "Date unknown."}
    right = dict(wrong, reason="Issue date is missing, so the wait period cannot be checked.")
    assert "exact reason" in investigation.call_problem("flag_for_human_review", wrong)
    assert investigation.call_problem("flag_for_human_review", right) is None


def test_lookups_must_use_the_requesting_employee():
    investigation = Investigation("E1003", "I need a monitor.")

    assert investigation.call_problem("get_employee_info", {"employee_id": "E1001"}) is not None
    assert investigation.call_problem("get_employee_info", {"employee_id": "e1003"}) is None


def test_rule_check_leaves_the_wording_to_the_model():
    request = "Can I get a spare laptop? I'd like to keep the one I have."
    investigation = Investigation("E1001", request)
    investigation.observe("get_employee_info", get_employee_info("E1001", as_of=AS_OF))
    arguments = {"employee_id": "E1001", "item": "laptop"}
    payload = check_request_eligibility("E1001", "laptop", as_of=AS_OF)
    investigation.observe("check_request_eligibility", payload, arguments)

    check = investigation.rule_check("check_request_eligibility", arguments, payload)
    assert "allowed as a replacement only" in check
    assert "Keeping the current laptop as well is not allowed." in check
    assert "Approved" not in check


def test_judgement_is_needed_once_the_data_settles_an_item():
    investigation = investigate("E1001", "Can I get a spare laptop? I'd like to keep the one I have.")

    assert investigation.needs_judgement()
    lines = investigation.allowance_lines()
    assert len(lines) == 1
    assert "replacement only" in lines[0]
    assert "return the oldest one (issued 2021-01-15)" in lines[0]

    judge(investigation, "The employee wants to keep the current laptop as well, which the policy does not cover.")
    assert not investigation.needs_judgement()
    assert investigation.decisions()[0]["disposition"] == "escalate"


def test_no_judgement_when_every_item_is_already_escalated():
    investigation = investigate("E1004", "Please replace my laptop.")

    assert not investigation.needs_judgement()


def test_allowance_under_the_max_and_for_a_denial():
    under = investigate("E1003", "I need a monitor.").allowance_lines()[0]
    assert "may have one more monitor" in under

    denied = investigate("E1001", "I need a new monitor.").allowance_lines()[0]
    assert "not allowed yet" in denied
    assert "the wait ends 2028-06-01" in denied


def test_rule_line_puts_the_decision_word_first():
    investigation = investigate("E1001", "Please replace my laptop.")

    line = rule_line(investigation.decisions()[0])
    assert line.startswith("laptop: Approved. Count 1 equals max 1")


def test_an_approved_replacement_says_the_oldest_is_returned():
    investigation = investigate("E1001", "Please replace my laptop.")

    reply = investigation.reply()
    assert "This is a replacement: the oldest laptop is returned." in reply


def test_rule_check_gives_the_exact_reason_when_the_data_requires_escalation():
    investigation = Investigation("E1004", "Please replace my laptop.")
    investigation.observe("get_employee_info", get_employee_info("E1004", as_of=AS_OF))
    arguments = {"employee_id": "E1004", "item": "laptop"}
    payload = check_request_eligibility("E1004", "laptop", as_of=AS_OF)
    investigation.observe("check_request_eligibility", payload, arguments)

    check = investigation.rule_check("check_request_eligibility", arguments, payload)
    assert "The data requires escalation." in check
    assert "Issue date is missing, so the wait period cannot be checked." in check


def test_rule_check_ignores_an_item_the_request_did_not_name():
    investigation = Investigation("E1003", "I need a monitor.")
    investigation.observe("get_employee_info", get_employee_info("E1003", as_of=AS_OF))
    investigation.observe("get_policy_limits", get_policy_limits("standard"))
    arguments = {"employee_id": "E1003", "item": "ergonomic monitor"}
    payload = check_request_eligibility("E1003", "ergonomic monitor", as_of=AS_OF)
    investigation.observe("check_request_eligibility", payload, arguments)

    check = investigation.rule_check("check_request_eligibility", arguments, payload)
    assert "not an item in this request" in check
    assert investigation.missing_step() == 'check_request_eligibility with item "monitor"'


def test_a_non_catalog_item_checked_by_name_settles_the_request():
    investigation = Investigation("E1003", "Can I get a standing desk?")
    investigation.observe("get_employee_info", get_employee_info("E1003", as_of=AS_OF))
    investigation.observe("get_policy_limits", get_policy_limits("standard"))
    arguments = {"employee_id": "E1003", "item": "standing desk"}
    investigation.observe(
        "check_request_eligibility", check_request_eligibility("E1003", "standing desk", as_of=AS_OF), arguments
    )

    assert investigation.missing_step() == (
        'flag_for_human_review with reason "Item is not in the equipment catalog, so no role limit applies."'
    )


def test_must_include_names_the_employee_and_every_case():
    investigation = investigate("E1001", "Can I get a spare laptop? I'd like to keep the one I have.")
    judge(investigation, "The employee wants to keep the current laptop as well.")

    assert must_include(investigation.employee, investigation.reviews) == ["Priya Shah", "ESC-001"]


def test_must_include_uses_the_id_for_an_unknown_employee():
    investigation = investigate("E9999", "Could I get a headset please?")

    assert must_include(investigation.employee, investigation.reviews) == ["E9999", "ESC-001"]


def test_outcome_of_an_approval():
    investigation = investigate("E1003", "Please send me a monitor, I don't have one at my desk.")

    result = outcome(investigation.decisions(), investigation.reviews, "match")
    assert result.decision == "approved"
    assert result.escalated_by is None
    assert result.case_ids == []
    assert [(item.item, item.disposition) for item in result.items] == [("monitor", "approve")]


def test_outcome_of_a_denial():
    investigation = investigate("E1001", "My monitor keeps going black, I need another monitor.")

    result = outcome(investigation.decisions(), investigation.reviews, "match")
    assert result.decision == "denied"
    assert result.escalated_by is None


def test_outcome_of_a_data_rule_escalation():
    investigation = investigate("E1004", "My laptop keeps freezing, can I have a new laptop?")

    result = outcome(investigation.decisions(), investigation.reviews, "skipped")
    assert result.decision == "escalated"
    assert result.escalated_by == "data_rule"
    assert result.case_ids == ["ESC-001"]
    assert result.items[0].reason_code == "missing_issue_date"


def test_outcome_of_a_model_escalation():
    investigation = investigate("E1001", "Can I get a spare laptop? I'd like to keep the one I have.")
    judge(investigation, "The employee wants to keep the current laptop as well.")

    result = outcome(investigation.decisions(), investigation.reviews, "match")
    assert result.decision == "escalated"
    assert result.escalated_by == "model_judgement"


def test_outcome_of_a_mixed_request():
    investigation = investigate("E1004", "I need a laptop and a headset.")

    result = outcome(investigation.decisions(), investigation.reviews, "match")
    assert result.decision == "mixed"
    assert result.escalated_by == "data_rule"


def test_outcome_when_reflection_fails_records_the_new_case():
    investigation = investigate("E1003", "Please send me a monitor, I don't have one at my desk.")
    review = flag_for_human_review("E1003", investigation.request, REPLY_NOT_CONFIRMED)

    result = outcome(investigation.decisions(), investigation.reviews, "not match", unconfirmed_review=review)
    assert result.decision == "escalated"
    assert result.escalated_by == "reply_not_confirmed"
    assert result.case_ids == [review["escalation_id"]]
    assert result.items[0].disposition == "approve"


def test_outcome_when_the_review_record_could_not_be_stored():
    investigation = investigate("E1003", "Please send me a monitor, I don't have one at my desk.")

    result = outcome(
        investigation.decisions(),
        investigation.reviews,
        "not match",
        unconfirmed_review={"error": "StorageError", "message": "disk full"},
    )
    assert result.decision == "none"


def test_outcome_with_no_decisions():
    assert outcome([], []).decision == "none"


def test_an_approval_is_reflected():
    investigation = investigate("E1003", "Please send me a monitor, I don't have one at my desk.")

    assert needs_reflection(investigation.decisions()) is True


def test_a_denial_is_reflected():
    investigation = investigate("E1001", "My monitor keeps going black, I need another monitor.")

    assert needs_reflection(investigation.decisions()) is True


def test_a_model_escalation_is_reflected():
    investigation = investigate("E1001", "Can I get a spare laptop? I'd like to keep the one I have.")
    judge(investigation, "The employee wants to keep the current laptop as well.")

    assert needs_reflection(investigation.decisions()) is True


def test_a_data_rule_escalation_is_not_reflected():
    investigation = investigate("E1004", "My laptop keeps freezing, can I have a new laptop?")

    assert needs_reflection(investigation.decisions()) is False


def test_a_data_rule_escalation_with_an_approval_is_reflected():
    investigation = investigate("E1004", "I need a laptop and a headset.")

    dispositions = [decision["disposition"] for decision in investigation.decisions()]
    assert "escalate" in dispositions and dispositions != ["escalate"] * len(dispositions)
    assert needs_reflection(investigation.decisions()) is True


def test_unconfirmed_reply_quotes_the_new_case():
    employee = get_employee_info("E1003", as_of=AS_OF)
    review = flag_for_human_review("E1003", "I need a monitor.", REPLY_NOT_CONFIRMED)

    reply = unconfirmed_reply(employee, review)
    assert reply.startswith("Escalated. Case ESC-001.")
    assert REPLY_NOT_CONFIRMED in reply
    assert "approved" not in reply.lower()


def test_reflection_reason_is_not_offered_to_the_model():
    assert REPLY_NOT_CONFIRMED not in reason_instructions()
