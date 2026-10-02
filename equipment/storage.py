import json
from pathlib import Path

from equipment.errors import DirectoryError


def read_json(path: Path):
    """Read a JSON file. Raises DirectoryError when the file or the JSON is bad."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise DirectoryError(f"Cannot read {path.name}") from error
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise DirectoryError(f"{path.name} is not valid JSON") from error
