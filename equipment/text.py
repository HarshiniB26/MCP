"""Small string helpers shared by the tools and the decision rules."""

import re


def normalize_space(value):
    """Trim and collapse internal whitespace. Case is preserved."""
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_text(value):
    """Trim, collapse whitespace, and lowercase."""
    return normalize_space(value).lower()


def normalize_id(value):
    """Trim and uppercase an employee id. Blank stays blank."""
    return (value or "").strip().upper()
