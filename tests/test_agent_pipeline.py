"""The production agent pipeline, end to end, with a scripted model in place of Ollama.

Each test runs the real agent._decide: it starts server.py over stdio, runs the
ReAct loop with the real guardrails, asks the judgement question, drafts, and
reflects. Only the model's answers are scripted, so every code path the real
model can trigger is exercised in CI without a model server.

Decisions are checked on the structured outcome code records, not on words in
the reply, so a reply that says "not approved" cannot pass as an approval.
"""

import json

import pytest

import agent
from equipment.errors import ModelError
from equipment.reasons import REPLY_NOT_CONFIRMED
from equipment.schemas import Judgement, Reflection, answer_schema

MONITOR_REQUEST = "Please send me a monitor, I don't have one at my desk."


def judgement(reason="The reason is ordinary.", **answers):
    fields = {"asks_for_something_else": False, "health_or_accessibility_need": False, "contradicts_record": False}
    fields.update(answers)
    return json.dumps({**fields, "reason": reason})


CLEAR = judgement()


def call(name, thinking="", content="", **arguments):
    return {
        "content": content,
        "thinking": thinking,
        "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
    }


def lookups(employee_id, role, *items):
    calls = [
        call("get_employee_info", "Find the employee.", employee_id=employee_id),
        call("get_policy_limits", "Find the role limits.", role=role),
    ]
    calls += [
        call("check_request_eligibility", f"Check the {item}.", employee_id=employee_id, item=item) for item in items
    ]
    return calls


def verdict(decision, matched, reason, final=""):
    return json.dumps(
        {
            "rule_decision": decision,
            "draft_decision": decision if matched else "Denied",
            "same_decision": matched,
            "must_appear_present": True,
            "nothing_invented": matched,
            "no_extra_promise": True,
            "sound_reasoning": True,
            "reason": reason,
            "final_answer": final,
        }
    )


class ScriptedModel:
    """Stands in for agent.chat. Answers each kind of call from a script and keeps what it was sent."""

    def __init__(self, react, judge=CLEAR, draft="", reflect=""):
        self.react = list(react)
        self.answers = {"judge": judge, "draft": draft, "reflect": reflect}
        self.calls = []

    def __call__(self, model, messages, tools, think=False, format=None):
        kind = self.kind(messages, tools)
        self.calls.append({"kind": kind, "messages": messages, "think": think, "format": format})
        if kind == "react":
            return self.react.pop(0) if self.react else {"content": "I have finished."}
        answer = self.answers[kind]
        if isinstance(answer, Exception):
            raise answer
        return {"content": answer}

    @staticmethod
    def kind(messages, tools):
        if tools:
            return "react"
        first = messages[0]["content"]
        if first.startswith("You are judging"):
            return "judge"
        if first.startswith("You are checking a drafted reply"):
            return "reflect"
        return "draft"

    def kinds(self):
        return [entry["kind"] for entry in self.calls]

    def first(self, kind):
        return next(entry for entry in self.calls if entry["kind"] == kind)

    def prompt(self, kind):
        return self.first(kind)["messages"][-1]["content"]


@pytest.fixture
def scripted(monkeypatch, run_agent):
    def run(model, employee_id, request_text):
        monkeypatch.setattr(agent, "chat", model)
        return run_agent("scripted", employee_id, request_text)

    return run


APPROVED_DRAFT = "Approved. Lena Cho may have a monitor: she has 0 of a maximum of 1."
IMPROVED = "Approved. Lena Cho (E1003) may have a monitor because she has 0 on file and the maximum is 1."


def approval_model(react=None, draft=APPROVED_DRAFT, reflect=None):
    return ScriptedModel(
        react if react is not None else lookups("E1003", "standard", "monitor"),
        draft=draft,
        reflect=reflect if reflect is not None else verdict("Approved", True, "The draft matches.", IMPROVED),
    )


def test_approval_runs_every_stage_and_uses_the_improved_reply(scripted):
    model = approval_model()

    record = scripted(model, "E1003", MONITOR_REQUEST)

    assert model.kinds() == ["react", "react", "react", "react", "judge", "draft", "reflect"]
    result = record.outcome
    assert result.decision == "approved"
    assert result.escalated_by is None
    assert result.reflection == "match"
    assert [(item.item, item.disposition) for item in result.items] == [("monitor", "approve")]
    assert record.final == IMPROVED
    assert f"draft: {APPROVED_DRAFT}" in record.text


def test_reflection_receives_the_full_react_trace_and_the_draft(scripted):
    model = approval_model()

    scripted(model, "E1003", MONITOR_REQUEST)

    prompt = model.prompt("reflect")
    assert "Thought: Find the employee." in prompt
    assert "Action: check_request_eligibility" in prompt
    assert '"max_on_file": 1' in prompt
    assert "Judgement answer:" in prompt
    assert "Rule: " in prompt
    assert APPROVED_DRAFT in prompt
    assert "- Lena Cho" in prompt


def test_react_and_judgement_think_and_the_judge_and_reflection_must_answer_in_the_schema(scripted):
    model = approval_model()

    scripted(model, "E1003", MONITOR_REQUEST)

    think = {entry["kind"]: entry["think"] for entry in model.calls}
    assert think == {"react": True, "judge": True, "draft": False, "reflect": False}
    assert model.first("judge")["format"] == answer_schema(Judgement)
    assert model.first("reflect")["format"] == answer_schema(Reflection)
    assert model.first("draft")["format"] is None
    judge_prompt = model.first("judge")["messages"][0]["content"]
    assert f'"{MONITOR_REQUEST}"' in judge_prompt
    assert "monitor: allowed" in judge_prompt


def test_reflection_catches_a_flawed_draft_and_escalates(scripted):
    flawed = "Denied. Lena Cho cannot have a monitor until 2030-01-01."
    model = approval_model(
        draft=flawed,
        reflect=verdict("Approved", False, "The draft denies a monitor the rules approve and invents 2030-01-01."),
    )

    record = scripted(model, "E1003", MONITOR_REQUEST)

    result = record.outcome
    assert result.decision == "escalated"
    assert result.escalated_by == "reply_not_confirmed"
    assert result.reflection == "not match"
    assert result.case_ids == ["ESC-001"]
    assert REPLY_NOT_CONFIRMED in record.final
    assert "2030" not in record.final
    assert "Failed checks: same_decision, nothing_invented." in record.text


def test_unreadable_reflection_escalates(scripted):
    model = approval_model(reflect="Verdict: MATCH. Looks fine to me.")

    record = scripted(model, "E1003", MONITOR_REQUEST)

    assert record.outcome.escalated_by == "reply_not_confirmed"
    assert agent.REFLECTION_UNREADABLE in record.text


def test_match_without_an_improved_reply_keeps_the_draft(scripted):
    model = approval_model(reflect=verdict("Approved", True, "The draft matches."))

    record = scripted(model, "E1003", MONITOR_REQUEST)

    assert record.outcome.decision == "approved"
    assert record.final == APPROVED_DRAFT


def test_draft_failure_escalates(scripted):
    model = approval_model(draft=ModelError("model offline"))

    record = scripted(model, "E1003", MONITOR_REQUEST)

    assert record.outcome.escalated_by == "reply_not_confirmed"
    assert record.outcome.reflection == "not match"
    assert "reflect" not in model.kinds()


def test_model_judgement_escalates_through_the_tool(scripted):
    reason = "The employee wants to keep the current laptop as well."
    draft = f"Escalated. Case ESC-001. Priya Shah asked for a second laptop. {reason}"
    model = ScriptedModel(
        lookups("E1001", "standard", "laptop"),
        judge=judgement(reason, asks_for_something_else=True),
        draft=draft,
        reflect=verdict("Escalated", True, "The draft matches."),
    )

    record = scripted(model, "E1001", "Can I get a spare laptop? I'd like to keep the one I have.")

    result = record.outcome
    assert result.decision == "escalated"
    assert result.escalated_by == "model_judgement"
    assert result.case_ids == ["ESC-001"]
    assert record.final == draft
    assert "Action: flag_for_human_review" in record.text
    assert f'"reason": "{reason}"' in record.text
    assert "laptop: Escalated." in model.prompt("reflect")


def test_judgement_is_decided_by_the_fields_not_the_words_in_the_reason(scripted):
    model = ScriptedModel(
        lookups("E1005", "standard", "headset"),
        judge=judgement("There is no need to escalate; the dates look fine.", contradicts_record=True),
        draft="Escalated. Case ESC-001. Riley Okada's headset request goes to a person.",
        reflect=verdict("Escalated", True, "The draft matches."),
    )

    record = scripted(model, "E1005", "My headset that I got back in 2020 crackles, please replace it.")

    assert record.outcome.escalated_by == "model_judgement"


def test_unreadable_judgement_escalates(scripted):
    model = ScriptedModel(
        lookups("E1003", "standard", "monitor"),
        judge="CLEAR: the reason is ordinary.",
        draft="Escalated. Case ESC-001. Lena Cho's monitor request goes to a person.",
        reflect=verdict("Escalated", True, "The draft matches."),
    )

    record = scripted(model, "E1003", MONITOR_REQUEST)

    assert [entry["kind"] for entry in model.calls].count("judge") == 2
    assert record.outcome.escalated_by == "model_judgement"
    assert agent.JUDGE_UNREADABLE in record.text


def test_data_rule_escalation_skips_judgement_draft_and_reflection(scripted):
    reason = "Issue date is missing, so the wait period cannot be checked."
    react = lookups("E1004", "standard", "laptop") + [
        call(
            "flag_for_human_review",
            "The rule check requires escalation.",
            employee_id="E1004",
            request="My laptop keeps freezing, can I have a new laptop?",
            reason=reason,
        )
    ]
    model = ScriptedModel(react)

    record = scripted(model, "E1004", "My laptop keeps freezing, can I have a new laptop?")

    assert set(model.kinds()) == {"react"}
    result = record.outcome
    assert result.decision == "escalated"
    assert result.escalated_by == "data_rule"
    assert result.reflection == "skipped"
    assert result.items[0].reason_code == "missing_issue_date"
    assert reason in record.final


def test_unknown_employee_escalates_without_a_draft(scripted):
    react = [
        call("get_employee_info", employee_id="E9999"),
        call(
            "flag_for_human_review",
            employee_id="E9999",
            request="Could I get a headset please?",
            reason="Employee id is not in the directory, so role and equipment cannot be checked.",
        ),
    ]
    model = ScriptedModel(react)

    record = scripted(model, "E9999", "Could I get a headset please?")

    assert record.outcome.escalated_by == "data_rule"
    assert record.outcome.items[0].reason_code == "unknown_employee"
    assert "draft" not in model.kinds()


def test_a_call_for_another_employee_is_refused(scripted):
    react = [call("get_employee_info", employee_id="E1002")] + lookups("E1003", "standard", "monitor")
    model = approval_model(react=react)

    record = scripted(model, "E1003", MONITOR_REQUEST)

    assert '"error": "NotRun"' in record.text
    assert 'Use employee_id \\"E1003\\" from the request.' in record.text
    assert record.outcome.decision == "approved"


def test_a_flag_for_a_settled_denial_is_refused_and_the_denial_stands(scripted):
    request = "My monitor keeps going black, I need another monitor."
    react = lookups("E1001", "standard", "monitor") + [
        call(
            "flag_for_human_review",
            "The rule check says not allowed yet, so I will escalate.",
            employee_id="E1001",
            request=request,
            reason="monitor: not allowed yet.",
        )
    ]
    model = ScriptedModel(
        react,
        draft="Denied. Priya Shah cannot have another monitor until 2028-06-01.",
        reflect=verdict("Denied", True, "The draft matches."),
    )

    record = scripted(model, "E1001", request)

    assert "do not escalate now" in record.text
    assert record.outcome.decision == "denied"
    assert record.outcome.case_ids == []


def test_a_model_that_answers_without_tools_is_nudged(scripted):
    react = [{"content": "Approved."}] + lookups("E1003", "standard", "monitor")
    model = approval_model(react=react)

    record = scripted(model, "E1003", MONITOR_REQUEST)

    assert "Guardrail: the model answered without a tool call." in record.text
    assert 'Still needed: get_employee_info with employee_id "E1003"' in record.text
    assert record.outcome.decision == "approved"


def test_agent_makes_the_required_calls_a_model_skips(scripted):
    react = [call("get_employee_info", employee_id="E1003")]
    model = approval_model(react=react)

    record = scripted(model, "E1003", MONITOR_REQUEST)

    assert "Guardrail step 1\nAgent: The model stopped before get_policy_limits" in record.text
    assert "Guardrail step 2" in record.text
    assert record.outcome.decision == "approved"


def test_thoughts_come_from_the_models_thinking_then_its_text(scripted):
    react = [
        call("get_employee_info", thinking="I should look up E1003 first.", employee_id="E1003"),
        call("get_policy_limits", content="Thought: Now the standard limits.", role="standard"),
        call("check_request_eligibility", employee_id="E1003", item="monitor"),
    ]
    model = approval_model(react=react)

    record = scripted(model, "E1003", MONITOR_REQUEST)

    assert "Thought: I should look up E1003 first." in record.text
    assert "Thought: Now the standard limits." in record.text
    assert f"Thought: {agent.NO_THOUGHT}\nAction: check_request_eligibility" in record.text
    assert "Thought: Call " not in record.text
