"""RE-DACT entity overlap merger.

Conforms to AGENTS.md section 5:
    def merge(ents: list[Entity]) -> list[Entity]: ...
    # higher score wins, then longer span; no overlaps out
"""

from __future__ import annotations

from redact.entity import Entity


def _overlaps(e1: Entity, e2: Entity) -> bool:
    """Return True if two entity spans overlap (i.e. share at least one character)."""
    return max(e1.start, e2.start) < min(e1.end, e2.end)


def merge(ents: list[Entity]) -> list[Entity]:
    """Resolve overlapping entity spans.

    Rules (AGENTS.md section 5 & 7):
      1. Higher score wins.
      2. If scores are tied, longer span wins.
      3. No overlapping entities in the returned list.
      4. Returned entities are ordered by start character offset.
    """
    if not ents:
        return []

    # Sort key: higher score first, then longer span first, then earlier start
    candidates = sorted(
        ents,
        key=lambda e: (-e.score, -(e.end - e.start), e.start),
    )

    accepted: list[Entity] = []

    for cand in candidates:
        # Check if candidate overlaps with any already accepted entity
        if any(_overlaps(cand, acc) for acc in accepted):
            continue
        accepted.append(cand)

    # Return accepted entities sorted in document order
    return sorted(accepted, key=lambda e: (e.start, e.end))
