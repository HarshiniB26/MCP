"""Decide approve / deny / escalate for each item, and record the outcome.

Code decides what the data settles: an unknown employee, an item outside the
catalog, a missing or future issue date, and whether the item is within the
role's limits. What the employee wrote is the model's judgement. The model may
escalate an item the data would approve or deny, but it cannot approve what the
data denies or deny what the data approves.
"""

import re

from equipment.reasons import CATALOG, REASON_TEXT
from equipment.schemas import ItemDecision, Outcome
from equipment.text import normalize_id, normalize_text

_ITEM = re.compile(r"\b(laptop|monitor|headset)s?\b", re.I)
MODEL_JUDGEMENT = "model_judgement"


def named_items(request):
    """Distinct catalog items in the order written. A sentence with none names itself."""
    text = normalize_text(request)
    found = []
    for match in _ITEM.finditer(text):
        item = match.group(1).lower()
        if item not in found:
            found.append(item)
    if found:
        return found
    fallback = re.sub(r"[^a-z0-9\s]", " ", text)
    fallback = normalize_text(fallback)
    return [fallback]


def wait_phrase(years):
    unit = "year" if years == 1 else "years"
    return f"wait is {years} {unit}"


def _decision(item, disposition, code, eligibility, rationale, reason_text=None):
    return {
        "item": item,
        "disposition": disposition,
        "reason_code": code,
        "reason_text": reason_text or REASON_TEXT.get(code),
        "eligibility": eligibility,
        "rationale": rationale,
        "review": None,
    }


def classify(eligibility):
    """What the data alone says about one eligibility result."""
    item = eligibility.get("item") or ""
    code = eligibility.get("undetermined_code")
    if not eligibility.get("found_employee") or code == "unknown_employee":
        return _decision(
            item,
            "escalate",
            "unknown_employee",
            eligibility,
            "The employee tool did not find this id, so the request cannot be decided from the file.",
        )
    if code == "item_not_in_catalog" or item not in CATALOG:
        return _decision(
            item,
            "escalate",
            "item_not_in_catalog",
            eligibility,
            "The item is outside the catalog, so no role limit applies.",
        )
    if code == "missing_issue_date":
        return _decision(
            item,
            "escalate",
            "missing_issue_date",
            eligibility,
            "Count equals the max and an issue date is missing, so the wait cannot be checked.",
        )
    if code == "invalid_issue_date":
        return _decision(
            item,
            "escalate",
            "invalid_issue_date",
            eligibility,
            "An issue date is after the as-of date, so the wait cannot be checked.",
        )

    count = eligibility.get("count")
    maximum = eligibility.get("max_on_file")
    if eligibility.get("outcome") == "eligible":
        if count is not None and count == maximum:
            rationale = (
                f"Count {count} equals max {maximum} for {item}, and the wait for the oldest one "
                f"finished on {eligibility.get('anniversary')} (as of {eligibility.get('as_of')}), "
                "so a replacement is within policy."
            )
        else:
            rationale = f"Count {count} is below max {maximum} for {item}, so it is within policy."
        return _decision(item, "approve", None, eligibility, rationale)
    if eligibility.get("outcome") == "ineligible" and eligibility.get("anniversary"):
        return _decision(
            item,
            "deny",
            None,
            eligibility,
            (
                f"The wait for {item} is unfinished until {eligibility.get('anniversary')} "
                f"(as of {eligibility.get('as_of')})."
            ),
        )
    if eligibility.get("outcome") == "ineligible":
        return _decision(
            item,
            "deny",
            None,
            eligibility,
            f"Count {count} is above max {maximum} for {item}, so the request is outside policy.",
        )
    return _decision(
        item,
        "escalate",
        "missing_issue_date",
        eligibility,
        "The eligibility result has no outcome that can be approved or denied.",
    )


def allowance(decision):
    """What the policy gives the employee for one item, in plain words."""
    eligibility = decision.get("eligibility") or {}
    item = decision["item"]
    count, maximum = eligibility.get("count"), eligibility.get("max_on_file")
    if decision["disposition"] == "approve":
        if count is not None and count == maximum:
            return (
                f"{item}: allowed as a replacement only. The employee has {count} of max {maximum}, "
                f"so they would get a new {item} and return the oldest one (issued {eligibility.get('oldest_issued_on')}). "
                f"Keeping the current {item} as well is not allowed."
            )
        return f"{item}: allowed. The employee has {count} of max {maximum}, so they may have one more {item}."
    if decision["disposition"] == "deny":
        if eligibility.get("anniversary"):
            return (
                f"{item}: not allowed yet. The employee has {count} of max {maximum}, the oldest was issued "
                f"{eligibility.get('oldest_issued_on')}, and the wait ends {eligibility['anniversary']}."
            )
        return f"{item}: not allowed. The employee has {count} of max {maximum}."
    return f"{item or 'request'}: already sent to a person. {decision['reason_text']}"


DECISION_WORD = {"approve": "Approved", "deny": "Denied", "escalate": "Escalated"}


def rule_line(decision):
    """One rule result with its decision word first, for the drafting and reflection prompts."""
    return f"{decision['item'] or 'request'}: {DECISION_WORD[decision['disposition']]}. {decision['rationale']}"


def policy_decisions(items, employee, eligibility_by_item):
    """One data decision per item. An unknown employee escalates every item."""
    if not employee.get("found"):
        shown = employee.get("employee_id") or "(blank)"
        return [
            _decision(
                item,
                "escalate",
                "unknown_employee",
                None,
                f"Employee {shown} is not in the directory, so this request cannot be decided from the file.",
            )
            for item in items
        ]
    return [classify(eligibility_by_item[item]) for item in items]


def _identity(employee):
    if employee.get("found"):
        return f"{employee['name']} ({employee['employee_id']}), role {employee['role']}"
    if employee.get("employee_id"):
        return f"Employee {employee['employee_id']} was not found"
    return "Employee id was blank"


def _limit_sentence(eligibility):
    if not eligibility:
        return ""
    parts = []
    if eligibility.get("count") is not None:
        parts.append(f"count {eligibility['count']}")
    if eligibility.get("max_on_file") is not None:
        parts.append(f"max {eligibility['max_on_file']}")
    if eligibility.get("wait_years") is not None:
        parts.append(wait_phrase(eligibility["wait_years"]))
    sentence = ""
    if parts:
        sentence = f" Item {eligibility.get('item')}: " + ", ".join(parts) + "."
    if eligibility.get("oldest_issued_on"):
        sentence += f" Oldest issued {eligibility['oldest_issued_on']}."
    if eligibility.get("anniversary"):
        sentence += f" Anniversary {eligibility['anniversary']}."
    if eligibility.get("completed_years") is not None:
        sentence += f" Completed years {eligibility['completed_years']}."
    return sentence


def _as_of(employee, eligibility):
    if eligibility and eligibility.get("as_of"):
        return eligibility["as_of"]
    return employee.get("as_of")


def compose_reply(employee, decisions, reviews):
    """A reply that states only facts the tools returned."""
    lines = []
    for decision in decisions:
        eligibility = decision.get("eligibility") or {}
        as_of = _as_of(employee, eligibility)
        limits = _limit_sentence(eligibility)
        identity = _identity(employee)
        if decision["disposition"] == "approve":
            replacement = ""
            if eligibility.get("count") is not None and eligibility.get("count") == eligibility.get("max_on_file"):
                replacement = f" This is a replacement: the oldest {decision['item']} is returned."
            lines.append(f"Approved. {identity}.{limits} As of {as_of} the request is within entitlement.{replacement}")
        elif decision["disposition"] == "deny":
            if eligibility.get("anniversary"):
                ending = f"As of {as_of} the wait is not finished."
            else:
                ending = f"As of {as_of} the request is outside entitlement."
            lines.append(f"Denied. {identity}.{limits} {ending}")
        else:
            review = decision.get("review") or {}
            item = decision["item"]
            item_bit = f" for {item}" if item in CATALOG else ""
            lines.append(
                f"Escalated. Case {review.get('escalation_id', 'not recorded')}{item_bit}. "
                f"{review.get('reason', decision['reason_text'])} "
                f"{identity}.{limits} As of {as_of}."
            )
    return "\n".join(lines)


def needs_reflection(decisions):
    """The model decided something: an approve, a deny, or its own escalation.

    A request escalated only by data rules has a fixed reply, so there is nothing to draft or check.
    """
    return any(
        decision["disposition"] != "escalate" or decision["reason_code"] == MODEL_JUDGEMENT for decision in decisions
    )


def unconfirmed_reply(employee, review):
    """The reply when reflection failed and the request went to a person."""
    if not review.get("escalation_id"):
        return f"No decision. The review record could not be stored: {review.get('message', 'unknown error')}"
    return (
        f"Escalated. Case {review['escalation_id']}. {review['reason']} "
        f"{_identity(employee)}. As of {employee.get('as_of')}."
    )


def fact_sheet(employee, decisions, reviews):
    """Every tool fact the drafting prompt lists for the model."""
    facts = []
    if employee.get("found"):
        facts.extend([employee["name"], employee["employee_id"], employee["role"]])
    elif employee.get("employee_id"):
        facts.append(employee["employee_id"])
    seen_dates = set()
    as_of = employee.get("as_of")
    if as_of:
        facts.append(as_of)
        seen_dates.add(as_of)
    for review in reviews:
        facts.append(review["escalation_id"])
        facts.append(review["reason"])
        if review.get("recorded_on"):
            seen_dates.add(review["recorded_on"])
    for decision in decisions:
        item = decision["item"]
        if item in CATALOG:
            facts.append(item)
        eligibility = decision.get("eligibility") or {}
        if eligibility.get("count") is not None:
            facts.append(f"count {eligibility['count']}")
        if eligibility.get("max_on_file") is not None:
            facts.append(f"max {eligibility['max_on_file']}")
        if eligibility.get("wait_years") is not None:
            facts.append(wait_phrase(eligibility["wait_years"]))
        if eligibility.get("oldest_issued_on"):
            facts.append(eligibility["oldest_issued_on"])
        if eligibility.get("anniversary"):
            facts.append(eligibility["anniversary"])
        if eligibility.get("completed_years") is not None:
            facts.append(f"completed years {eligibility['completed_years']}")
        if eligibility.get("as_of") and eligibility["as_of"] not in seen_dates:
            facts.append(eligibility["as_of"])
            seen_dates.add(eligibility["as_of"])
    return facts


def must_include(employee, reviews):
    """What the reply has to name: the employee and every case id."""
    entries = []
    if employee.get("found"):
        entries.append(employee["name"])
    elif employee.get("employee_id"):
        entries.append(employee["employee_id"])
    entries.extend(review["escalation_id"] for review in reviews if review.get("escalation_id"))
    return entries


_OVERALL = {
    frozenset({"approve"}): "approved",
    frozenset({"deny"}): "denied",
    frozenset({"escalate"}): "escalated",
}


def outcome(decisions, reviews, reflection=None, unconfirmed_review=None):
    """The decision as recorded by code: per-item dispositions, who escalated, and the case ids."""
    items = [
        ItemDecision(item=d["item"] or "request", disposition=d["disposition"], reason_code=d["reason_code"])
        for d in decisions
    ]
    case_ids = [review["escalation_id"] for review in reviews if review.get("escalation_id")]
    if unconfirmed_review is not None:
        if not unconfirmed_review.get("escalation_id"):
            return Outcome(decision="none", items=items, case_ids=case_ids, reflection=reflection)
        return Outcome(
            decision="escalated",
            escalated_by="reply_not_confirmed",
            items=items,
            case_ids=case_ids + [unconfirmed_review["escalation_id"]],
            reflection=reflection,
        )
    kinds = frozenset(d["disposition"] for d in decisions)
    escalated_by = None
    if any(d["reason_code"] == MODEL_JUDGEMENT for d in decisions):
        escalated_by = "model_judgement"
    elif "escalate" in kinds:
        escalated_by = "data_rule"
    return Outcome(
        decision=_OVERALL.get(kinds, "mixed" if kinds else "none"),
        escalated_by=escalated_by,
        items=items,
        case_ids=case_ids,
        reflection=reflection,
    )


def describe(step):
    """A tool call in words, for messages to the model and the trace."""
    name, arguments = step
    if name == "get_employee_info":
        return f'get_employee_info with employee_id "{arguments["employee_id"]}"'
    if name == "get_policy_limits":
        return f'get_policy_limits with role "{arguments["role"]}"'
    if name == "check_request_eligibility":
        return f'check_request_eligibility with item "{arguments["item"]}"'
    return f'flag_for_human_review with reason "{arguments["reason"]}"'


class Investigation:
    """What the tools have returned so far, which call is still required, and the decision."""

    def __init__(self, employee_id, request):
        self.employee_id = employee_id
        self.request = request
        self.items = named_items(request)
        self.employee = None
        self.policy = None
        self.eligibility = {}
        self.required_reviews = []
        self.judgement = None
        self.failed = None

    @property
    def reviews(self):
        """Every review record in the order it was stored."""
        records = list(self.required_reviews)
        if self.judgement:
            records.append(self.judgement)
        return sorted(records, key=lambda record: record.get("escalation_id", ""))

    def observe(self, name, payload, arguments=None):
        if not isinstance(payload, dict) or payload.get("error"):
            message = ""
            if isinstance(payload, dict):
                message = payload.get("message") or payload.get("error") or ""
            self.failed = message or f"{name} failed."
            return
        if name == "get_employee_info":
            self.employee = payload
        elif name == "get_policy_limits":
            self.policy = payload
            if not payload.get("found"):
                self.failed = f"No entitlement is on file for role {payload.get('role') or ''}."
        elif name == "check_request_eligibility":
            requested = (arguments or {}).get("item")
            if requested:
                self.eligibility[requested] = payload
            returned = payload.get("item")
            if returned:
                self.eligibility[returned] = payload
            if payload.get("undetermined_code") == "item_not_in_catalog" and self.items[0] not in CATALOG:
                self.eligibility.setdefault(self.items[0], payload)
        elif name == "flag_for_human_review":
            step = self._next_required_flag()
            if step and payload.get("reason") == step[1]["reason"]:
                self.required_reviews.append(payload)
            else:
                self.judgement = payload
        else:
            self.failed = f"Unknown tool {name}."

    def _lookups_done(self):
        if self.failed or self.employee is None:
            return False
        if not self.employee.get("found"):
            return True
        return self.policy is not None and all(item in self.eligibility for item in self.items)

    def _policy_decisions(self):
        return policy_decisions(self.items, self.employee, self.eligibility)

    def decisions(self):
        """The data decision per item, with the model's escalation applied to items the data would settle."""
        required = iter(self.required_reviews)
        result = []
        for decision in self._policy_decisions():
            if decision["disposition"] == "escalate":
                decision["review"] = next(required, None)
            elif self.judgement:
                policy_said = "approve" if decision["disposition"] == "approve" else "deny"
                decision = _decision(
                    decision["item"],
                    "escalate",
                    MODEL_JUDGEMENT,
                    decision["eligibility"],
                    (
                        f"The data alone would {policy_said} this, but the model escalated after "
                        f"reading the request: {self.judgement['reason']}"
                    ),
                    reason_text=self.judgement["reason"],
                )
                decision["review"] = self.judgement
            result.append(decision)
        return result

    def next_action(self):
        """The next call the data requires, as (tool name, arguments), or None."""
        if self.failed:
            return None
        if self.employee is None:
            return ("get_employee_info", {"employee_id": self.employee_id})
        if self.employee.get("found"):
            if self.policy is None:
                return ("get_policy_limits", {"role": self.employee["role"]})
            for item in self.items:
                if item not in self.eligibility:
                    return (
                        "check_request_eligibility",
                        {"employee_id": self.employee.get("employee_id") or self.employee_id, "item": item},
                    )
        return self._next_required_flag()

    def _next_required_flag(self):
        if not self._lookups_done():
            return None
        required = [d for d in self._policy_decisions() if d["disposition"] == "escalate"]
        if len(self.required_reviews) >= len(required):
            return None
        decision = required[len(self.required_reviews)]
        return (
            "flag_for_human_review",
            {
                "employee_id": self.employee.get("employee_id") or self.employee_id,
                "request": self.request,
                "reason": decision["reason_text"],
            },
        )

    def _item_key(self, arguments, payload):
        for candidate in ((arguments or {}).get("item"), (payload or {}).get("item")):
            if candidate in self.items:
                return candidate
        if self.items[0] not in CATALOG and (payload or {}).get("undetermined_code") == "item_not_in_catalog":
            return self.items[0]
        return None

    def rule_check(self, name, arguments, payload):
        """A note for the model after a lookup: what the data says, and what is left to its judgement."""
        if not isinstance(payload, dict) or payload.get("error"):
            return None
        if name == "get_employee_info" and not payload.get("found"):
            return (
                "Rule check: the employee is not in the directory, so the data requires escalation. "
                f'Call flag_for_human_review with reason "{REASON_TEXT["unknown_employee"]}".'
            )
        if name != "check_request_eligibility":
            return None
        key = self._item_key(arguments, payload)
        if key is None:
            wanted = ", ".join(item for item in self.items if item not in self.eligibility) or "none"
            return f"Rule check: {(arguments or {}).get('item')!r} is not an item in this request. Items still to check: {wanted}."
        decision = classify(self.eligibility[key])
        label = key if key in CATALOG else "the requested item"
        if decision["disposition"] == "escalate":
            return (
                f"Rule check for {label}: {decision['rationale']} The data requires escalation. "
                f'When every item is checked, call flag_for_human_review with reason "{decision["reason_text"]}".'
            )
        return (
            f"Rule check: {allowance(decision)} "
            "When every item is checked, you will be asked whether the employee's words fit what the policy allows."
        )

    def needs_judgement(self):
        """True when the data settled at least one item and the model has not judged the wording yet."""
        if self.judgement or not self._lookups_done() or self.next_action() is not None:
            return False
        return any(d["disposition"] in ("approve", "deny") for d in self._policy_decisions())

    def allowance_lines(self):
        return [f"- {allowance(decision)}" for decision in self._policy_decisions()]

    def call_problem(self, name, arguments, judging=False):
        """Why the agent should not run a tool call the model proposed, or None when it may run.

        Once the data settles every item, only the judgement step (judging=True) may escalate,
        so the model's own escalation always goes through the structured judgement answer.
        """
        arguments = arguments or {}
        if name in ("get_employee_info", "check_request_eligibility", "flag_for_human_review"):
            if normalize_id(arguments.get("employee_id")) != normalize_id(self.employee_id):
                return f'Use employee_id "{self.employee_id}" from the request.'
        if name == "get_policy_limits" and self.employee and self.employee.get("found"):
            if normalize_text(arguments.get("role")) != self.employee["role"]:
                return f'Use role "{self.employee["role"]}" from get_employee_info.'
        if name != "flag_for_human_review":
            return None
        if self.failed:
            return f"The investigation cannot continue: {self.failed}"
        given = (arguments.get("reason") or "").strip().strip("\"'")
        step = self.next_action()
        if step and step[0] != "flag_for_human_review":
            return f"Not yet. First call {describe(step)}."
        if step:
            if given != step[1]["reason"]:
                return f'The data requires this exact reason: "{step[1]["reason"]}".'
            return None
        if self.judgement:
            return f"This request is already escalated as {self.judgement['escalation_id']}. Write the decision."
        if not any(d["disposition"] in ("approve", "deny") for d in self._policy_decisions()):
            return "Every item is already escalated. Write the decision."
        if not given:
            return "Write a one-sentence reason that says what in the request makes it unclear."
        if not judging:
            return (
                "The data settles every item, so do not escalate now. When the investigation is done, "
                "you will be asked whether the employee's words need a person."
            )
        return None

    def missing_step(self):
        """What is still needed before a decision, in words, or None."""
        step = self.next_action()
        return describe(step) if step else None

    def incomplete_reason(self):
        if self.failed:
            return f"No decision. {self.failed}"
        if self.employee is None or self.next_action() is not None:
            return "No decision. The investigation stopped before the tools finished."
        required = [d for d in self._policy_decisions() if d["disposition"] == "escalate"]
        if len(required) != len(self.required_reviews):
            return "No decision. The review records do not match the escalation rules."
        for decision, review in zip(required, self.required_reviews):
            if review.get("reason") != decision["reason_text"]:
                return "No decision. A review record does not match the policy reason."
        return None

    def reply(self):
        reason = self.incomplete_reason()
        if reason:
            return reason
        return compose_reply(self.employee, self.decisions(), self.reviews)
