from equipment.traceability import LOG_FILE, RunRecord


def test_a_run_is_appended_with_start_and_finish_times(tmp_path, monkeypatch):
    import equipment.traceability as traceability

    monkeypatch.setattr(traceability, "LOG_FILE", tmp_path / "traceability.log")
    record = RunRecord("E1003", "I need a monitor.")
    record.add("draft: Approved.")
    record.finish("Approved. Lena Cho has no monitor on file.")

    text = traceability.LOG_FILE.read_text()
    assert text.startswith("=" * 72)
    assert "started:" in text
    assert "finished:" in text
    assert "employee: E1003" in text
    assert "request:  I need a monitor." in text
    assert "final:" in text
    assert "Approved. Lena Cho has no monitor on file." in text
    assert LOG_FILE.name == "traceability.log"
