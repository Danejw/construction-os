# construction_os/services/artifact_review.py
from __future__ import annotations

import hashlib
from typing import Literal, Sequence

from construction_os.retrieval.types import EvidenceItem

ReviewAggregateStatus = Literal["passed", "needs_review"]

_NEEDS_REVIEW_SOURCE = frozenset({"unsupported", "contradicted"})
_NEEDS_REVIEW_MEMORY = frozenset({"memory_conflict"})


def content_hash(content: str) -> str:
    normalized = (content or "").strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def exclude_self_evidence(
    items: Sequence[EvidenceItem], note_id: str
) -> list[EvidenceItem]:
    nid = str(note_id)
    return [
        item
        for item in items
        if str(item.id) != nid and str(item.parent_id or "") != nid
    ]


def aggregate_review_status(
    *,
    source_verdicts: Sequence[str],
    memory_verdicts: Sequence[str],
) -> ReviewAggregateStatus:
    if any(v in _NEEDS_REVIEW_SOURCE for v in source_verdicts):
        return "needs_review"
    if any(v in _NEEDS_REVIEW_MEMORY for v in memory_verdicts):
        return "needs_review"
    return "passed"


def apply_claim_spans(
    content: str, replacements: Sequence[tuple[str, str]]
) -> tuple[str, list[str]]:
    """Replace first exact occurrence of each claim_span; skip missing spans."""
    updated = content
    skipped: list[str] = []
    for span, fix in replacements:
        if not span or span not in updated:
            skipped.append(span)
            continue
        updated = updated.replace(span, fix, 1)
    return updated, skipped
