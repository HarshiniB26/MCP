"""The evaluation cases through the real model. Needs a running Ollama, so CI skips it.

Run inside the container:
    LIVE_AGENT=1 python -m pytest -m live -v

Each case checks the structured outcome code recorded (the decision, who escalated,
and the reflection result), not words in the reply, so a reply that says "not
approved" cannot pass as an approval and a request escalated only because
reflection failed does not count as a correct escalation.
"""

import os

import pytest

import agent
from evaluate import CASES

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("LIVE_AGENT") != "1", reason="needs a running Ollama model; set LIVE_AGENT=1"),
]


@pytest.mark.parametrize(
    ("employee_id", "request_text", "decision", "escalated_by", "reflection"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_real_model_reaches_the_expected_decision(
    run_agent, employee_id, request_text, decision, escalated_by, reflection
):
    record = run_agent(agent.configured_model(), employee_id, request_text)

    result = record.outcome
    assert (result.decision, result.escalated_by, result.reflection) == (decision, escalated_by, reflection), (
        record.text
    )
    if decision == "escalated":
        assert result.case_ids, "an escalation must have a stored case"
