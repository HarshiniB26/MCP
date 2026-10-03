"""Typed shapes for what the model must answer and for the decision the agent records.

The judgement and reflection calls send these schemas to Ollama as the required
answer format, so the model fills in yes/no fields instead of writing words that
code would have to search for. Code derives escalate and match from the fields.
"""

from typing import Literal

from pydantic import BaseModel, Field, ValidationError


class Judgement(BaseModel):
    asks_for_something_else: bool = Field(
        description=(
            "True if the employee asks for something other than one new or replacement item for themselves, "
            "such as keeping their current item as well, or an item for someone else."
        )
    )
    health_or_accessibility_need: bool = Field(
        description="True if the employee describes a health or accessibility need."
    )
    contradicts_record: bool = Field(
        description="True if a year, date, age, or count the employee states differs from the record."
    )
    reason: str = Field(min_length=1, description="One sentence explaining the answers.")

    @property
    def escalate(self):
        return self.asks_for_something_else or self.health_or_accessibility_need or self.contradicts_record


class Reflection(BaseModel):
    rule_decision: str = Field(description="Approved, Denied, or Escalated for each item, from the rule results.")
    draft_decision: str = Field(description="Approved, Denied, or Escalated for each item, as the draft states it.")
    same_decision: bool = Field(description="True if the draft gives every item the same decision as the rule results.")
    must_appear_present: bool = Field(
        description="True if the draft contains every entry listed under 'Must appear in the draft'."
    )
    nothing_invented: bool = Field(
        description="True if every name, date, count, maximum, wait, and case id in the draft matches the tools."
    )
    no_extra_promise: bool = Field(description="True if the draft promises nothing beyond what the tools allow.")
    sound_reasoning: bool = Field(
        description="True if the trace looked up the employee, the role limits, and every item, and the rule results follow."
    )
    reason: str = Field(min_length=1, description="One sentence explaining the verdict.")
    final_answer: str = Field(
        default="",
        description="If every check is true, the draft rewritten as a clear two-to-four-sentence reply. Otherwise empty.",
    )

    @property
    def checks(self):
        return {
            "same_decision": self.same_decision,
            "must_appear_present": self.must_appear_present,
            "nothing_invented": self.nothing_invented,
            "no_extra_promise": self.no_extra_promise,
            "sound_reasoning": self.sound_reasoning,
        }

    @property
    def matched(self):
        return all(self.checks.values())

    def failed_checks(self):
        return [name for name, passed in self.checks.items() if not passed]


class ItemDecision(BaseModel):
    item: str
    disposition: Literal["approve", "deny", "escalate"]
    reason_code: str | None = None


class Outcome(BaseModel):
    """The decision the agent reached, from code's records rather than from the reply's wording."""

    decision: Literal["approved", "denied", "escalated", "mixed", "none"]
    escalated_by: Literal["data_rule", "model_judgement", "reply_not_confirmed"] | None = None
    items: list[ItemDecision] = Field(default_factory=list)
    case_ids: list[str] = Field(default_factory=list)
    reflection: Literal["match", "not match", "skipped"] | None = None

    def summary(self):
        text = self.decision
        if self.escalated_by:
            text += f" by {self.escalated_by.replace('_', ' ')}"
        if self.case_ids:
            text += f", case {', '.join(self.case_ids)}"
        return text


def answer_schema(model_class):
    return model_class.model_json_schema()


def read_answer(model_class, text):
    """The model's JSON answer as model_class, or None when it does not fit the schema."""
    try:
        return model_class.model_validate_json(text or "")
    except ValidationError:
        return None
