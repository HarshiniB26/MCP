"""Catalog items and the reason sentences for escalations the data itself requires.

An escalation because of what the employee wrote is the model's judgement,
and the model writes that reason in its own words.
"""

CATALOG = ("laptop", "monitor", "headset")

REASON_TEXT = {
    "unknown_employee": (
        "Employee id is not in the directory, so role and equipment cannot be checked."
    ),
    "item_not_in_catalog": (
        "Item is not in the equipment catalog, so no role limit applies."
    ),
    "missing_issue_date": "Issue date is missing, so the wait period cannot be checked.",
    "invalid_issue_date": "Issue date is in the future, so the wait period cannot be checked.",
}

# Used by the agent itself when its reply fails reflection.
REPLY_NOT_CONFIRMED = (
    "The drafted reply did not match the tool results, so a person must confirm the decision."
)


def reason_instructions():
    """How the model words the reason when it calls flag_for_human_review."""
    return "\n".join(
        [
            "When you call flag_for_human_review:",
            "- If a Rule check says the data requires escalation, copy the reason it gives exactly.",
            "- If you escalate because of what the employee wrote, write one plain sentence in your own words "
            "that says what in the request makes it unclear.",
        ]
    )
