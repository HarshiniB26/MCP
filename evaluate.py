"""Run new requests through the real model and save the scores to results/eval_results.json.

Needs a running Ollama, so run it inside the container and commit the results file:
    python evaluate.py

CI cannot reach the model, so it checks the committed file instead. None of these
requests are the demo questions in run_demo.sh. Each case is scored on the outcome
code recorded (the decision, who escalated, and the reflection result), never on
words in the reply.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import agent
from equipment.traceability import MemoryRecord

RESULTS_FILE = Path(__file__).resolve().parent / "results" / "eval_results.json"

# The denial holds until 2028-02-29, when the wait for E1005's laptop ends.
CASES = [
    ("approve", "E1003", "I take a lot of calls, could I get a headset?", "approved", None, "match"),
    ("deny", "E1005", "My laptop battery dies fast, can I get a new laptop?", "denied", None, "match"),
    ("missing_date", "E1004", "Could you swap my laptop for a newer one?", "escalated", "data_rule", "skipped"),
    (
        "keep_both",
        "E1002",
        "Can I get a spare headset? I'd like to keep the one I have.",
        "escalated",
        "model_judgement",
        "match",
    ),
    ("for_someone_else", "E1003", "Can I get a headset for my new teammate?", "escalated", "model_judgement", "match"),
    (
        "health",
        "E1003",
        "My back hurts when I work, so I need a different monitor.",
        "escalated",
        "model_judgement",
        "match",
    ),
    ("unknown_employee", "E7777", "Could I get a monitor please?", "escalated", "data_rule", "skipped"),
    (
        "contradiction",
        "E1005",
        "My headset that I got back in 2020 crackles, please replace it.",
        "escalated",
        "model_judgement",
        "match",
    ),
]

METRICS = {
    "decision_accuracy": "decision",
    "escalation_source_accuracy": "escalated_by",
    "reflection_accuracy": "reflection",
}


def run_case(model, case_id, employee_id, request_text, decision, escalated_by, reflection):
    record = MemoryRecord()
    asyncio.run(agent._decide(model, employee_id, request_text, record))
    result = record.outcome
    expected = {"decision": decision, "escalated_by": escalated_by, "reflection": reflection}
    actual = {field: getattr(result, field) for field in expected}
    return {
        "id": case_id,
        "employee_id": employee_id,
        "request": request_text,
        "expected": expected,
        "actual": actual,
        "case_ids": result.case_ids,
        "passed": {field: actual[field] == expected[field] for field in expected},
        "final_answer": record.final,
    }


def summarize(rows):
    summary = {}
    for metric, field in METRICS.items():
        passed = sum(row["passed"][field] for row in rows)
        summary[metric] = {"score": passed / len(rows), "passed": passed, "total": len(rows)}
    return summary


def main():
    model = agent.configured_model()
    rows = []
    for case in CASES:
        row = run_case(model, *case)
        rows.append(row)
        verdict = "pass" if all(row["passed"].values()) else "FAIL"
        print(f"{verdict}  {row['id']}: {row['actual']}")
    data = {
        "model": model,
        "run_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "summary": summarize(rows),
        "cases": rows,
    }
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for metric, score in data["summary"].items():
        print(f"{metric}={score['score']:.3f} ({score['passed']}/{score['total']})")


if __name__ == "__main__":
    main()
