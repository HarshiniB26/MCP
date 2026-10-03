# IT Equipment Request Handler

| | |
|---|---|
| Document ID | IT-EQ-REQ-001 |
| Version | 2.0 |
| Status | Approved for build |
| Date | 2026-10-02 |

An employee asks for equipment in plain language. The handler looks up the person and that role’s entitlement, then returns one disposition per catalog item: approve, deny, or escalate.

Approve and deny are final. Escalate stores a review record and does not guess the reviewer’s decision.

Synthetic data only. No purchasing, budget, shipping, login, or reviewer screen. The review queue lives in memory and clears when the process exits.

Identifiers used here:

| Kind | Example | Meaning |
|---|---|---|
| Policy | P1–P8 | The rule |
| Reason code | `unknown_employee` | Why a review record exists. P5 codes have fixed text. `model_judgement` uses the model's own sentence |
| Behavior | FR-1–FR-6 | What the software does |
| Case id | `ESC-001` | One queue row. Not a policy |

## Rules

### P1. Catalog

Standard issue is `laptop`, `monitor`, and `headset`. Any other item has no entitlement.

### P2. Entitlement

| Role | Item | Max on file | Wait |
|---|---|---|---|
| standard | laptop | 1 | 4 years |
| standard | monitor | 1 | 3 years |
| standard | headset | 1 | 2 years |
| manager | laptop | 1 | 2 years |
| manager | monitor | 2 | 2 years |
| manager | headset | 1 | 1 year |

Hire date is stored. It does not change entitlement.

### P3. Wait

- The anniversary is the issue date plus the wait, same month and day.
- If that day does not exist, use the last day of the month. 29 February in a non-leap year becomes 28 February. In a leap year it stays 29 February.
- The wait is finished on the anniversary day and after. The day before is outside entitlement.
- Live calls use the real local date, `date.today()`.
- A caller may pass a date. When it does not, the real local date is used.

### P4. Quantity

- Count rows for that item.
- Count below the max is within entitlement. Do not read issue dates.
- Count equal to the max is a replacement of the oldest unit. It is within entitlement only when that issue date exists, is on or before the as-of date, and the wait is finished.
- A newer row of the same item does not move the oldest issue date.

### P5. The data requires a person

Some requests cannot be decided from the file. These escalate whatever the request says, in this order, with this exact text:

| Order | Reason code | When | Text |
|---|---|---|---|
| 1 | `unknown_employee` | Id is blank or not in the directory | Employee id is not in the directory, so role and equipment cannot be checked. |
| 2 | `item_not_in_catalog` | Item is outside P1 | Item is not in the equipment catalog, so no role limit applies. |
| 3 | `missing_issue_date` | Count equals max and a matching issue date is missing | Issue date is missing, so the wait period cannot be checked. |
| 4 | `invalid_issue_date` | Count equals max and a matching issue date is after the as-of date | Issue date is in the future, so the wait period cannot be checked. |

### P6. The model judges what the employee wrote

When the data settles an item (P4 within or outside entitlement), the model reads the whole request and decides whether the employee's words make it unclear enough that a person should decide. There is no word list. Examples a person should see: a health or accessibility need, an item for another person, an extra unit while keeping the current one, or a description of the equipment that contradicts the record. An ordinary reason such as "it is slow" does not escalate.

- After every item is checked, the agent asks the model one question that shows what the policy allows in plain words (for example, "allowed as a replacement only; keeping the current laptop as well is not allowed") next to the employee's words. The model must answer in the `Judgement` JSON schema (`equipment/schemas.py`): three true/false fields (`asks_for_something_else`, `health_or_accessibility_need`, `contradicts_record`) and a one-sentence `reason`. Code escalates if any field is true; the words in the reason never decide.
- On escalate, `flag_for_human_review` is called once with the model's sentence. The reason code is `model_judgement`. An answer that does not fit the schema escalates rather than guessing.
- During the investigation the model may only call `flag_for_human_review` for a P5 data rule. Once the data settles every item, the agent refuses any other flag call, so the model's own escalation always goes through the structured judgement answer.
- The model can only turn approve or deny into escalate. It cannot approve an item outside entitlement or deny an item within it.

### P7. Clear decision

- No escalation and P4 within entitlement: approve.
- No escalation and P4 outside entitlement: deny.
- A deny does not call `flag_for_human_review`.

Several items in one sentence:

- Decide each distinct catalog item in the order written. `and` and `or` are both handled this way.
- One review record per P5 item. A model escalation is one record that covers every item the data would have approved or denied.
- Approve and deny in the same sentence still stand when there is no model escalation.

### P8. Reply

- State only facts a tool returned on this request: identity, role, count, max, wait, oldest issue date, anniversary, as-of date, disposition, and, if escalated, the case id and reason text.
- Do not add a loaner, an exception, a price, a backorder, or a different anniversary.
- Before the draft is final, the model compares it with the tool results and answers in the `Reflection` JSON schema: five true/false checks (`same_decision`, `must_appear_present`, `nothing_invented`, `no_extra_promise`, `sound_reasoning`), a `reason`, and a `final_answer`. Code says MATCH only if all five are true. Other wording is fine; wrong or invented facts, a different decision, or promising more than the tools allow are NOT MATCH.
- On MATCH, the same call's `final_answer` rewrites the draft as a clear two-to-four-sentence reply: the decision, the reason from the tool results, and what happens next, with the same facts. That reply is final; if none is given, the draft is final.
- On NOT MATCH, or a verdict that cannot be read, there is no retry: the request is escalated.
- Reflection runs when the model decided something: an approve, a deny, or its own escalation (P6). When every item was escalated by a data rule (P5), the reply is the stored review record and reflection is skipped.

### Request fields

| Field | Rule |
|---|---|
| `employee_id` | Required. Trimmed. Case-insensitive match. Stored in uppercase. Blank is unknown |
| `item` | One item per entitlement check. Trimmed, lowercased, internal spaces collapsed. ` Monitor ` is `monitor` |
| `reason` | Required. Trimmed, internal spaces collapsed |

Role, hire date, and equipment are looked up.

## Directory

The people are not listed here. They are stored in `employees.json`, and the functions read that file. This document holds the rules. The JSON holds the records. A new person or a new date is a change to the file only.

Each record has `employee_id`, `name`, `role`, `hired_on`, and `equipment`. Each equipment row has `item` and `issued_on`. `issued_on` may be null. `role` is `standard` or `manager`.

An id that is not in the file is unknown. The file does not store a future issue date.

## Workflow

1. Read `employee_id`, the items named, and `reason`.
2. Look up the employee and the role’s entitlement.
3. For each item, apply P5, then P4.
4. Call `flag_for_human_review` once per P5 item, then let the model judge the wording (P6).
5. Draft the reply from tool facts only.
6. Run the P8 check. Rewrite once if it fails.

## Tools

Each tool is a plain function first, then exposed by the server. Dates are `YYYY-MM-DD` or null.

### FR-1. `get_employee_info(employee_id)`

Reads `employees.json`.

- Unknown or blank: `found` false, normalized id or `""`, `as_of`.
- Known: `found` true, id, `name`, `role`, `hired_on`, `tenure_years` (informational), `equipment` as `{item, issued_on}` in directory order, `as_of`.

### FR-2. `get_policy_limits(role)`

Returns the P2 limits for that role.

- Unknown role: `found` false.
- `standard` or `manager`: `found` true, and `limits` with `item`, `max_on_file`, `wait_years` from P2.

### FR-3. `check_request_eligibility(employee_id, item)`

Applies P1–P5. Does not read the employee's words; that is P6, the model's judgement.

Returns `employee_id`, `item`, `as_of`, `found_employee`, `role`, `outcome` (`eligible`, `ineligible`, or `undetermined`), `undetermined_code`, `count`, `max_on_file`, `wait_years`, `oldest_issued_on`, `anniversary`, and `completed_years`. Use null when a value cannot be computed. `eligible` is the numeric limit only. It is not an approval.

### FR-4. `flag_for_human_review(employee_id, request, reason)`

Appends one record. Does not approve, deny, or delete.

| Field | Value |
|---|---|
| `escalation_id` | `ESC-001`, then `ESC-002`. Restarts when the process starts |
| `employee_id` | normalized |
| `request` | the employee’s text |
| `reason` | the P5 text, or the model's own sentence for P6. Blank is rejected |
| `recorded_on` | real local date |

### FR-5. Agent

Connects as a client. The model chooses each tool call and judges the wording (P6). The agent refuses calls that break P5 or P6, and makes any P5 call the model skipped. The trace shows Thought, Action, and Observation for every call, then the disposition. The ReAct turns run with thinking on, and each Thought is the model's own thinking for that call (or its text, or "(the model gave no reason with this call)"). Lines written by code are labelled `Agent:` or `Rule:`, never `Thought:`. At the end the agent writes a `decision:` line to the traceability log: the `Outcome` (decision, who escalated, per-item dispositions, case ids, reflection result), built by code from its own records, not from the reply text. The CLI prints a one-line `Decision:` summary.

### FR-6. Reflection

Performs P8. One model call judges the draft (`prompts/reflect.txt`). It receives the employee's request, the full ReAct trace (every Thought, Action, and Observation, the rule checks, and the judgement), the rule results, the facts, the names and case ids that must appear, and the draft. It checks the decision, the facts, that nothing extra is promised, and that the reasoning in the trace supports the decision. Code validates the JSON with Pydantic and derives the verdict from the five checks. On NOT MATCH there is no rewrite: the agent escalates the request instead of sending an unconfirmed decision. The CLI prints `Reflection: match`, `Reflection: not match`, or `Reflection: skipped` and the final answer; the reason goes to the traceability log.

### FR-7. Tests

Unit and integration tests under `tests/`, run by CI on every push.
