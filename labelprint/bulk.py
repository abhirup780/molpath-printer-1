"""Turn a pasted lab list into a clean list of Sales IDs.

Lab lists arrive in every shape: one ID per line, a column copied out of Excel
(tab separated), a comma list from an email, or a whole table with headers and
dates. Rather than asking anyone to tidy that up, this splits on any separator,
keeps the tokens that look like Sales IDs, and reports everything it discarded
so nothing disappears silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Anything that is not part of an identifier is a separator: commas, tabs,
# newlines, semicolons, pipes, spaces, quotes, brackets.
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_-]*")

# A Sales ID is letters then digits, e.g. PR9000001. This deliberately rejects
# spreadsheet headers ("SalesID", "Patient") and dates ("25-03-2026").
DEFAULT_PATTERN = r"^[A-Za-z]{1,4}[0-9]{4,}$"


@dataclass
class ParseResult:
    ids: list[str] = field(default_factory=list)
    """Unique Sales IDs, in the order they first appeared."""

    repeated: dict[str, int] = field(default_factory=dict)
    """IDs that appeared more than once, and how many times."""

    skipped: list[str] = field(default_factory=list)
    """Tokens that did not look like a Sales ID, de-duplicated."""

    @property
    def summary(self) -> str:
        parts = [f"{len(self.ids)} Sales ID(s)"]
        if self.repeated:
            parts.append(f"{len(self.repeated)} repeated")
        if self.skipped:
            parts.append(f"{len(self.skipped)} ignored")
        return ", ".join(parts)


def parse(text: str, pattern: str = DEFAULT_PATTERN) -> ParseResult:
    """Extract Sales IDs from arbitrary pasted text."""
    try:
        matcher = re.compile(pattern)
    except re.error:
        matcher = re.compile(DEFAULT_PATTERN)

    result = ParseResult()
    seen: dict[str, int] = {}
    skipped_seen: set[str] = set()

    for match in TOKEN_RE.finditer(text or ""):
        token = match.group(0).upper()
        if not matcher.match(token):
            if token not in skipped_seen:
                skipped_seen.add(token)
                result.skipped.append(token)
            continue
        if token in seen:
            seen[token] += 1
        else:
            seen[token] = 1
            result.ids.append(token)

    result.repeated = {k: v for k, v in seen.items() if v > 1}
    return result
