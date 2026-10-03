from pathlib import Path

from equipment.schemas import Judgement, Reflection, answer_schema


def test_agent_prompts_are_present():
    root = Path(__file__).resolve().parents[1] / "prompts"
    for name in ("system", "decide_now", "reflect", "judge"):
        text = (root / f"{name}.txt").read_text(encoding="utf-8").strip()
        assert text


def test_reflection_prompt_receives_the_full_trace_and_the_draft():
    text = (Path(__file__).resolve().parents[1] / "prompts" / "reflect.txt").read_text(encoding="utf-8")
    for placeholder in ("{request}", "{trace}", "{rules}", "{facts}", "{must_include}", "{draft}"):
        assert placeholder in text


def test_judge_and_reflect_prompts_name_every_field_of_their_schema():
    root = Path(__file__).resolve().parents[1] / "prompts"
    for name, model_class in (("judge", Judgement), ("reflect", Reflection)):
        text = (root / f"{name}.txt").read_text(encoding="utf-8")
        for field in answer_schema(model_class)["properties"]:
            assert field in text, f"{name}.txt does not mention {field}"
