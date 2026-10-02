"""Append one record each time the agent runs.

Each run is appended to logs/traceability.log. A record has the time the run
started, the time it finished, the request, and the decision.
"""

from datetime import datetime
from pathlib import Path

from equipment.errors import DirectoryError

LOG_FILE = Path(__file__).resolve().parents[1] / "logs" / "traceability.log"


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class RunRecord:
    def __init__(self, employee_id, request_text, model=""):
        self.started = _now()
        self._closed = False
        self._lines = [
            "=" * 72,
            f"started:  {self.started}",
            f"employee: {employee_id}",
            f"request:  {request_text}",
        ]
        if model:
            self._lines.append(f"model: {model}")

    def add(self, text):
        if text:
            self._lines.append(text.rstrip())

    def finish(self, final, status="completed"):
        if self._closed:
            return
        self._lines.append("-" * 72)
        self._lines.append(f"status: {status}")
        self._lines.append(f"finished: {_now()}")
        self._lines.append("final:")
        self._lines.append((final or "No decision.").rstrip())
        self._lines.append("")
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with LOG_FILE.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(self._lines) + "\n")
        except OSError as error:
            raise DirectoryError(f"Cannot write {LOG_FILE.name}") from error
        self._closed = True
