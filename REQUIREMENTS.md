# IT Equipment Request Handler

| | |
|---|---|
| Document ID | IT-EQ-REQ-001 |
| Version | 1.8 |
| Status | Approved for build |
| Date | 2026-10-02 |

An employee asks for equipment in plain language. The handler looks up the person and that role’s entitlement, then returns one disposition per catalog item: approve, deny, or escalate.

Approve and deny are final. Escalate stores a review record and does not guess the reviewer’s decision.

Synthetic data only. No purchasing, budget, shipping, login, or reviewer screen. The review queue lives in memory and clears when the process exits.

Identifiers used here:

| Kind | Example | Meaning |
|---|---|---|
| Policy | P1–P8 | The rule |
| Reason code | `unknown_employee` | Stored on a review record. The set is closed |
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

### P5. A person must decide

Use the first matching reason code. Do not also approve or deny.

Match the normalized reason, case-insensitive, on whole words or phrases. `second` does not match inside `secondary`.

| Order | Reason code | When |
|---|---|---|
| 1 | `unknown_employee` | Id is blank or not in the directory |
| 2 | `item_not_in_catalog` | Item is outside P1 |
| 3 | `reason_outside_policy` | Reason contains `doctor`, `medical`, `disability`, `ergonomic`, `accommodation`, `neck pain`, `wrist pain`, `for my team`, `shared`, `for my intern`, `for a new hire`, or `someone else`. Applies even when P4 is within or outside entitlement |
| 4 | `missing_issue_date` | Count equals max and a matching issue date is missing |
| 5 | `invalid_issue_date` | Count equals max and a matching issue date is after the as-of date |
| 6 | `statement_conflicts_with_record` | A real issue date exists, and the reason has a year from 1990–2099 at least 2 years from that issue year, or a number before `year` / `years` at least 2 away from completed years. One conflict is enough. Applies even when P4 would deny |
| 7 | `replacement_versus_extra` | Count equals max, the wait is finished, and the reason contains `second`, `third`, `fourth`, `another`, `extra`, `additional`, `one more`, `as well`, `in addition`, `keep my current`, or `keep both` |

Order 7 does not apply while the wait is unfinished. The request then falls through to P6.

Words outside these lists do not escalate.

Text stored with the code:

| Reason code | Text |
|---|---|
| `unknown_employee` | Employee id is not in the directory, so role and equipment cannot be checked. |
| `item_not_in_catalog` | Item is not in the equipment catalog, so no role limit applies. |
| `reason_outside_policy` | Reason asks for shared, third-party, or accommodation use, which these limits do not decide. |
| `missing_issue_date` | Issue date is missing, so the wait period cannot be checked. |
| `invalid_issue_date` | Issue date is in the future, so the wait period cannot be checked. |
| `statement_conflicts_with_record` | The reason describes a different equipment age than the file, so the file cannot be treated as settled. |
| `replacement_versus_extra` | Policy allows replacing the oldest item, but the reason asks for an extra unit. |

### P6. Clear decision

- No P5 match and P4 within entitlement: approve.
- No P5 match and P4 outside entitlement: deny.
- A deny does not call `flag_for_human_review`.

### P7. Several items in one sentence

- Decide each distinct catalog item in the order written. `and` and `or` are both handled this way.
- Use the same reason for each item.
- An accommodation or shared-use phrase applies to every item in the sentence.
- An age or year is compared with that item’s own issue date.
- An extra-unit phrase is compared with that item’s own count and wait.
- One review record per escalated item. Approve and deny in the same sentence still stand.
- Do not add a reason code for “several items.”

### P8. Reply

- State only facts a tool returned on this request: identity, role, count, max, wait, oldest issue date, anniversary, as-of date, disposition, and, if escalated, the case id and reason text.
- Do not add a loaner, an exception, a price, a backorder, or a different anniversary.
- Check the draft against those facts before it is final.
- If the draft says approved or denied for an escalated item, rewrite it from the tool results and check once more.

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
3. For each item, run P5 in order, then P4 and P6.
4. Call `flag_for_human_review` once per escalated item.
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

Applies P1–P4 and the P5 codes that do not read wording: `unknown_employee`, `item_not_in_catalog`, `missing_issue_date`, `invalid_issue_date`.

Does not apply `reason_outside_policy`, `statement_conflicts_with_record`, or `replacement_versus_extra`.

Returns `employee_id`, `item`, `as_of`, `found_employee`, `role`, `outcome` (`eligible`, `ineligible`, or `undetermined`), `undetermined_code`, `count`, `max_on_file`, `wait_years`, `oldest_issued_on`, `anniversary`, and `completed_years`. Use null when a value cannot be computed. `eligible` is the numeric limit only. It is not an approval.

### FR-4. `flag_for_human_review(employee_id, request, reason)`

Appends one record. Does not approve, deny, or delete.

| Field | Value |
|---|---|
| `escalation_id` | `ESC-001`, then `ESC-002`. Restarts when the process starts |
| `employee_id` | normalized |
| `request` | the employee’s text |
| `reason` | the P5 text |
| `recorded_on` | real local date |

### FR-5. Agent

Connects as a client and calls the tools. Does not keep a second directory. The trace shows Thought, Action, and Observation for every call, then the disposition. Applies the three wording codes FR-3 skips.

### FR-6. Reflection

Performs P8. A draft that says approved or denied for an item that was escalated fails the check and is rewritten from the tool results.
