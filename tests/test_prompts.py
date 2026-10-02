from pathlib import Path


def test_agent_prompts_are_present():
    root = Path(__file__).resolve().parents[1] / "prompts"
    for name in ("system", "decide_now", "reflect", "judge"):
        text = (root / f"{name}.txt").read_text(encoding="utf-8").strip()
        assert text
