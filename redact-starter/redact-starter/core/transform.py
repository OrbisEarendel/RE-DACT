"""Turns spans into edits. Owner: P3.

STUB: every action except "keep" becomes a mask for now.
TODO (P3): real generalize (age -> range, date -> month/year) and fake (keyed hash + Faker).
"""
from core.policy import action_for
from core.types import Edit, Span


def make_replacement(span: Span, action: str) -> str:
    if action == "mask":
        return f"[{span.type}]"
    if action in ("generalize", "fake"):
        return f"[{span.type}]"  # TODO: replace with real behavior
    return span.text


def build_edits(spans: list[Span], level: int, overrides: dict | None = None) -> list[Edit]:
    edits = []
    for span in spans:
        action = action_for(span.type, level, overrides)
        if action == "keep":
            continue
        edits.append(Edit(span=span, replacement=make_replacement(span, action)))
    return edits
