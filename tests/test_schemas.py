"""The typed answers the model must give, and how code reads them.

The verdict comes from true/false fields, never from words in the text, so a
reason that says "no need to escalate" cannot flip the result.
"""

import json

from equipment.schemas import Judgement, Outcome, Reflection, answer_schema, read_answer


def judgement(**fields):
    answer = {
        "asks_for_something_else": False,
        "health_or_accessibility_need": False,
        "contradicts_record": False,
        "reason": "An ordinary replacement.",
    }
    answer.update(fields)
    return json.dumps(answer)


def reflection(**fields):
    answer = {
        "rule_decision": "monitor: Approved",
        "draft_decision": "monitor: Approved",
        "same_decision": True,
        "must_appear_present": True,
        "nothing_invented": True,
        "no_extra_promise": True,
        "sound_reasoning": True,
        "reason": "The draft states the approval and the facts from the tools.",
        "final_answer": "Approved. Lena Cho may have a monitor.",
    }
    answer.update(fields)
    return json.dumps(answer)


def test_judgement_with_every_answer_false_is_clear():
    answer = read_answer(Judgement, judgement())
    assert answer.escalate is False


def test_any_true_answer_escalates():
    for field in ("asks_for_something_else", "health_or_accessibility_need", "contradicts_record"):
        assert read_answer(Judgement, judgement(**{field: True})).escalate is True


def test_judgement_reason_words_do_not_decide():
    escalate = read_answer(Judgement, judgement(contradicts_record=True, reason="There is no need to escalate."))
    clear = read_answer(Judgement, judgement(reason="ESCALATE: this must go to a person."))

    assert escalate.escalate is True
    assert clear.escalate is False


def test_judgement_without_a_reason_cannot_be_read():
    assert read_answer(Judgement, judgement(reason="")) is None


def test_reflection_matches_only_when_every_check_is_true():
    assert read_answer(Reflection, reflection()).matched is True
    for field in ("same_decision", "must_appear_present", "nothing_invented", "no_extra_promise", "sound_reasoning"):
        answer = read_answer(Reflection, reflection(**{field: False}))
        assert answer.matched is False
        assert answer.failed_checks() == [field]


def test_reflection_reason_words_do_not_decide():
    answer = read_answer(Reflection, reflection(nothing_invented=False, reason="MATCH. Not a problem at all."))
    assert answer.matched is False


def test_answers_that_do_not_fit_the_schema_cannot_be_read():
    assert read_answer(Judgement, "ESCALATE: they want to keep both.") is None
    assert read_answer(Judgement, '{"contradicts_record": "maybe", "reason": "x"}') is None
    assert read_answer(Reflection, "Verdict: MATCH") is None
    assert read_answer(Reflection, "") is None
    assert read_answer(Reflection, None) is None


def test_schema_sent_to_the_model_lists_every_field_and_no_derived_verdict():
    judge_fields = set(answer_schema(Judgement)["properties"])
    reflect_fields = set(answer_schema(Reflection)["properties"])

    assert judge_fields == {"asks_for_something_else", "health_or_accessibility_need", "contradicts_record", "reason"}
    assert "escalate" not in judge_fields
    assert "matched" not in reflect_fields
    assert {"same_decision", "nothing_invented", "final_answer"} <= reflect_fields


def test_outcome_summary():
    assert Outcome(decision="approved").summary() == "approved"
    assert (
        Outcome(decision="escalated", escalated_by="model_judgement", case_ids=["ESC-001"]).summary()
        == "escalated by model judgement, case ESC-001"
    )
