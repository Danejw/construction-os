# tests/test_artifact_review.py
import pytest
from pydantic import ValidationError

from construction_os.domain.artifact_review import ArtifactReviewRun
from construction_os.retrieval.types import EvidenceItem
from construction_os.services.artifact_review import (
    aggregate_review_status,
    apply_claim_spans,
    content_hash,
    exclude_self_evidence,
)


def test_content_hash_stable():
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")


def test_exclude_self_evidence():
    items = [
        EvidenceItem(id="chunk:1", parent_id="note:self", score=0.9, source="vector"),
        EvidenceItem(id="note:self", parent_id=None, score=0.8, source="vector"),
        EvidenceItem(id="chunk:2", parent_id="source:other", score=0.7, source="vector"),
    ]
    kept = exclude_self_evidence(items, "note:self")
    assert len(kept) == 1
    assert kept[0].parent_id == "source:other"


def test_aggregate_needs_review_on_unsupported_or_memory_conflict():
    assert aggregate_review_status(
        source_verdicts=["supported", "not_in_corpus", "opinion"],
        memory_verdicts=["memory_aligned", "memory_novel"],
    ) == "passed"
    assert aggregate_review_status(
        source_verdicts=["unsupported"],
        memory_verdicts=[],
    ) == "needs_review"
    assert aggregate_review_status(
        source_verdicts=["supported"],
        memory_verdicts=["memory_conflict"],
    ) == "needs_review"
    assert aggregate_review_status(
        source_verdicts=["contradicted"],
        memory_verdicts=[],
    ) == "needs_review"


def test_apply_claim_spans_replaces_and_skips_missing():
    content, skipped = apply_claim_spans(
        "The budget is $1M. Scope includes HVAC.",
        [("The budget is $1M.", "The budget is $1.2M."), ("missing span", "x")],
    )
    assert "The budget is $1.2M." in content
    assert skipped == ["missing span"]


def test_artifact_review_run_default_status():
    run = ArtifactReviewRun(
        note_id="note:abc",
        project_id="project:xyz",
        content_hash="deadbeef",
    )
    assert run.status == "pending"
    assert run.table_name == "artifact_review_run"


def test_artifact_review_run_rejects_invalid_status():
    with pytest.raises(ValidationError):
        ArtifactReviewRun(
            note_id="note:abc",
            project_id="project:xyz",
            content_hash="deadbeef",
            status="bogus",  # type: ignore[arg-type]
        )
