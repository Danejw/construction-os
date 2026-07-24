# tests/test_artifact_review.py
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from construction_os.domain.artifact_review import ArtifactReviewRun
from construction_os.exceptions import InvalidInputError, NotFoundError
from construction_os.retrieval.types import EvidenceBundle, EvidenceItem
from construction_os.services.artifact_review import (
    ClaimFinding,
    ClaimSegment,
    MemoryFinding,
    ReviewReport,
    SegmentResult,
    _merge_reports,
    aggregate_review_status,
    apply_claim_spans,
    apply_review_fixes,
    content_hash,
    exclude_self_evidence,
    is_run_stale,
    run_artifact_review,
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


def test_is_run_stale():
    run = ArtifactReviewRun(
        note_id="note:abc",
        project_id="project:xyz",
        content_hash=content_hash("original"),
    )
    assert is_run_stale(run, "original") is False
    assert is_run_stale(run, "changed") is True


class _FakeRun:
    def __init__(
        self,
        run_id: str,
        *,
        note_id: str = "note:self",
        project_id: str = "project:xyz",
        content: str = "The budget is $1M.",
        findings: Optional[dict[str, Any]] = None,
    ) -> None:
        self.id = run_id
        self.note_id = note_id
        self.project_id = project_id
        self.status = "pending"
        self.findings: Optional[dict[str, Any]] = findings
        self.summary: Optional[dict[str, Any]] = None
        self.error_message: Optional[str] = None
        self.finished_at = None
        self.content_hash = content_hash(content)

    async def save(self) -> None:
        return None


async def _setup_run_review_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    judge_report: ReviewReport,
) -> _FakeRun:
    fake_run = _FakeRun("artifact_review_run:1")
    artifact = SimpleNamespace(
        id="note:self",
        content="The budget is $1M.",
    )

    async def fake_get_run(run_id: str) -> _FakeRun:
        assert run_id == "artifact_review_run:1"
        return fake_run

    async def fake_get_artifact(note_id: str) -> Any:
        assert note_id == "note:self"
        return artifact

    async def fake_mark_running(run_id: str) -> _FakeRun:
        fake_run.status = "running"
        return fake_run

    async def fake_complete(
        *,
        run_id: str,
        status: str,
        findings: dict[str, Any],
        summary: dict[str, Any],
    ) -> _FakeRun:
        fake_run.status = status
        fake_run.findings = findings
        fake_run.summary = summary
        return fake_run

    async def fake_fail(*, run_id: str, error_message: str) -> _FakeRun:
        fake_run.status = "failed"
        fake_run.error_message = error_message
        return fake_run

    async def fake_retrieve(query: str, **_kwargs: Any) -> EvidenceBundle:
        return EvidenceBundle(
            items=[
                EvidenceItem(
                    id="chunk:1",
                    parent_id="note:self",
                    score=0.9,
                    source="vector",
                    content="self should be excluded",
                ),
                EvidenceItem(
                    id="chunk:2",
                    parent_id="source:other",
                    score=0.8,
                    source="vector",
                    content="Budget is one million dollars.",
                ),
            ]
        )

    invoke_calls = {"n": 0}

    async def fake_invoke(
        messages: Any,
        schema: Any,
        **_kwargs: Any,
    ) -> Any:
        invoke_calls["n"] += 1
        if schema is SegmentResult:
            return SegmentResult(
                claims=[
                    ClaimSegment(
                        finding_id="claim_1",
                        claim_text="The budget is $1M.",
                    )
                ]
            )
        if schema is ReviewReport:
            return judge_report
        raise AssertionError(f"Unexpected schema: {schema}")

    monkeypatch.setattr(
        "construction_os.services.artifact_review.ArtifactReviewRun.get",
        fake_get_run,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.ProjectArtifact.get",
        fake_get_artifact,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.mark_run_running",
        fake_mark_running,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.complete_run",
        fake_complete,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.fail_run",
        fake_fail,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.retrieve",
        fake_retrieve,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.invoke_structured",
        fake_invoke,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.get_project_memory",
        AsyncMock(return_value=None),
    )
    return fake_run


@pytest.mark.asyncio
async def test_run_artifact_review_needs_review_when_unsupported(monkeypatch):
    judge_report = ReviewReport(
        claims=[
            ClaimFinding(
                finding_id="claim_1",
                claim_text="The budget is $1M.",
                source_verdict="unsupported",
                confidence=0.7,
                rationale="No matching budget in sources",
            )
        ],
        memory_findings=[],
    )
    fake_run = await _setup_run_review_mocks(monkeypatch, judge_report=judge_report)

    result = await run_artifact_review(
        note_id="note:self",
        project_id="project:xyz",
        run_id="artifact_review_run:1",
    )

    assert result.status == "needs_review"
    assert fake_run.status == "needs_review"
    assert fake_run.findings is not None
    assert fake_run.findings["claims"][0]["source_verdict"] == "unsupported"


@pytest.mark.asyncio
async def test_run_artifact_review_passed_for_benign_verdicts(monkeypatch):
    judge_report = ReviewReport(
        claims=[
            ClaimFinding(
                finding_id="claim_1",
                claim_text="The budget is $1M.",
                source_verdict="supported",
                confidence=0.9,
                evidence_ids=["chunk:2"],
                rationale="Matches source",
            ),
            ClaimFinding(
                finding_id="claim_2",
                claim_text="Looks great",
                source_verdict="opinion",
                confidence=0.8,
                rationale="Subjective",
            ),
            ClaimFinding(
                finding_id="claim_3",
                claim_text="Unknown detail",
                source_verdict="not_in_corpus",
                confidence=0.5,
                rationale="No evidence",
            ),
        ],
        memory_findings=[
            MemoryFinding(
                finding_id="claim_1",
                claim_text="The budget is $1M.",
                memory_verdict="memory_aligned",
                fact_id="fact_budget",
                rationale="Matches memory",
            ),
            MemoryFinding(
                finding_id="mem_novel",
                claim_text="Unknown detail",
                memory_verdict="memory_novel",
                rationale="New detail",
            ),
        ],
    )
    fake_run = await _setup_run_review_mocks(monkeypatch, judge_report=judge_report)

    # Segment returns one claim; judge mock returns the full benign report.
    async def fake_invoke(messages: Any, schema: Any, **_kwargs: Any) -> Any:
        if schema is SegmentResult:
            return SegmentResult(
                claims=[
                    ClaimSegment(finding_id="claim_1", claim_text="The budget is $1M."),
                    ClaimSegment(
                        finding_id="claim_2",
                        claim_text="Looks great",
                        is_opinion=True,
                    ),
                    ClaimSegment(
                        finding_id="claim_3",
                        claim_text="Unknown detail",
                    ),
                ]
            )
        if schema is ReviewReport:
            return judge_report
        raise AssertionError(f"Unexpected schema: {schema}")

    monkeypatch.setattr(
        "construction_os.services.artifact_review.invoke_structured",
        fake_invoke,
    )

    result = await run_artifact_review(
        note_id="note:self",
        project_id="project:xyz",
        run_id="artifact_review_run:1",
    )

    assert result.status == "passed"
    assert fake_run.status == "passed"
    assert fake_run.summary is not None
    assert fake_run.summary["claim_count"] == 3
    assert fake_run.summary["memory_finding_count"] == 2


def test_merge_reports_namespaces_memory_finding_ids_across_batches():
    """Colliding memory ids across batches must not drop later memory_conflict."""
    batch0 = ReviewReport(
        claims=[
            ClaimFinding(
                finding_id="claim_1",
                claim_text="Budget is $1M",
                source_verdict="supported",
            )
        ],
        memory_findings=[
            MemoryFinding(
                finding_id="memory_1",
                claim_text="Budget is $1M",
                memory_verdict="memory_aligned",
                rationale="Matches",
            )
        ],
    )
    batch1 = ReviewReport(
        claims=[
            ClaimFinding(
                finding_id="claim_2",
                claim_text="Deadline is June",
                source_verdict="supported",
            )
        ],
        memory_findings=[
            MemoryFinding(
                finding_id="memory_1",
                claim_text="Deadline is June",
                memory_verdict="memory_conflict",
                rationale="Memory says July",
            )
        ],
    )
    merged = _merge_reports([batch0, batch1], truncated=False)
    assert len(merged.memory_findings) == 2
    assert {m.finding_id for m in merged.memory_findings} == {
        "b0:memory_1",
        "b1:memory_1",
    }
    assert any(m.memory_verdict == "memory_conflict" for m in merged.memory_findings)
    assert aggregate_review_status(
        source_verdicts=[c.source_verdict for c in merged.claims],
        memory_verdicts=[m.memory_verdict for m in merged.memory_findings],
    ) == "needs_review"


@pytest.mark.asyncio
async def test_apply_review_fixes_stale_run(monkeypatch):
    content = "The budget is $1M."
    report = ReviewReport(
        claims=[
            ClaimFinding(
                finding_id="claim_1",
                claim_text="The budget is $1M.",
                source_verdict="unsupported",
                claim_span="The budget is $1M.",
                suggested_fix="The budget is $1.2M.",
            )
        ]
    )
    fake_run = _FakeRun(
        "artifact_review_run:1",
        content="original different content",
        findings=report.model_dump(),
    )
    artifact = SimpleNamespace(id="note:self", content=content)

    async def fake_get_artifact(note_id: str) -> Any:
        return artifact

    async def fake_get_run(run_id: str) -> _FakeRun:
        return fake_run

    monkeypatch.setattr(
        "construction_os.services.artifact_review.ProjectArtifact.get",
        fake_get_artifact,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.ArtifactReviewRun.get",
        fake_get_run,
    )

    with pytest.raises(InvalidInputError, match="stale"):
        await apply_review_fixes(
            note_id="note:self",
            run_id="artifact_review_run:1",
            finding_ids=["claim_1"],
        )


@pytest.mark.asyncio
async def test_apply_review_fixes_applies_claim_span(monkeypatch):
    content = "The budget is $1M. Scope includes HVAC."
    report = ReviewReport(
        claims=[
            ClaimFinding(
                finding_id="claim_1",
                claim_text="The budget is $1M.",
                source_verdict="unsupported",
                claim_span="The budget is $1M.",
                suggested_fix="The budget is $1.2M.",
            ),
            ClaimFinding(
                finding_id="claim_2",
                claim_text="Scope includes HVAC.",
                source_verdict="unsupported",
                claim_span="Scope includes HVAC.",
                suggested_fix="Scope includes HVAC and plumbing.",
            ),
        ]
    )
    fake_run = _FakeRun(
        "artifact_review_run:1",
        content=content,
        findings=report.model_dump(),
    )
    artifact = SimpleNamespace(id="note:self", content=content, saved=False)

    async def fake_get_artifact(note_id: str) -> Any:
        return artifact

    async def fake_get_run(run_id: str) -> _FakeRun:
        return fake_run

    async def fake_save() -> None:
        artifact.saved = True

    artifact.save = fake_save

    monkeypatch.setattr(
        "construction_os.services.artifact_review.ProjectArtifact.get",
        fake_get_artifact,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.ArtifactReviewRun.get",
        fake_get_run,
    )

    updated, skipped = await apply_review_fixes(
        note_id="note:self",
        run_id="artifact_review_run:1",
        finding_ids=["claim_1"],
    )

    assert updated.content == "The budget is $1.2M. Scope includes HVAC."
    assert skipped == []
    assert artifact.saved is True


@pytest.mark.asyncio
async def test_apply_review_fixes_skips_missing_spans(monkeypatch):
    content = "The budget is $1M."
    report = ReviewReport(
        claims=[
            ClaimFinding(
                finding_id="claim_1",
                claim_text="gone",
                source_verdict="unsupported",
                claim_span="This span is not in the content",
                suggested_fix="replacement",
            )
        ]
    )
    fake_run = _FakeRun(
        "artifact_review_run:1",
        content=content,
        findings=report.model_dump(),
    )
    artifact = SimpleNamespace(id="note:self", content=content, saved=False)

    async def fake_get_artifact(note_id: str) -> Any:
        return artifact

    async def fake_get_run(run_id: str) -> _FakeRun:
        return fake_run

    async def fake_save() -> None:
        artifact.saved = True

    artifact.save = fake_save

    monkeypatch.setattr(
        "construction_os.services.artifact_review.ProjectArtifact.get",
        fake_get_artifact,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.ArtifactReviewRun.get",
        fake_get_run,
    )

    updated, skipped = await apply_review_fixes(
        note_id="note:self",
        run_id="artifact_review_run:1",
        finding_ids=["claim_1"],
    )

    assert updated.content == content
    assert skipped == ["This span is not in the content"]
    assert artifact.saved is False


@pytest.mark.asyncio
async def test_apply_review_fixes_rejects_mismatched_note(monkeypatch):
    content = "The budget is $1M."
    report = ReviewReport(
        claims=[
            ClaimFinding(
                finding_id="claim_1",
                claim_text="The budget is $1M.",
                source_verdict="unsupported",
                claim_span="The budget is $1M.",
                suggested_fix="The budget is $1.2M.",
            )
        ]
    )
    fake_run = _FakeRun(
        "artifact_review_run:1",
        note_id="note:other",
        content=content,
        findings=report.model_dump(),
    )
    artifact = SimpleNamespace(id="note:self", content=content)

    async def fake_get_artifact(note_id: str) -> Any:
        return artifact

    async def fake_get_run(run_id: str) -> _FakeRun:
        return fake_run

    monkeypatch.setattr(
        "construction_os.services.artifact_review.ProjectArtifact.get",
        fake_get_artifact,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.ArtifactReviewRun.get",
        fake_get_run,
    )

    with pytest.raises(NotFoundError, match="Review run not found"):
        await apply_review_fixes(
            note_id="note:self",
            run_id="artifact_review_run:1",
            finding_ids=["claim_1"],
        )


@pytest.mark.asyncio
async def test_run_artifact_review_fails_run_on_load_error(monkeypatch):
    fake_run = _FakeRun("artifact_review_run:1")
    fail_called = {"n": 0}

    async def fake_get_run(run_id: str) -> _FakeRun:
        return fake_run

    async def fake_get_artifact(note_id: str) -> Any:
        raise RuntimeError("db unavailable")

    async def fake_fail(*, run_id: str, error_message: str) -> _FakeRun:
        fail_called["n"] += 1
        fake_run.status = "failed"
        fake_run.error_message = error_message
        return fake_run

    monkeypatch.setattr(
        "construction_os.services.artifact_review.ArtifactReviewRun.get",
        fake_get_run,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.ProjectArtifact.get",
        fake_get_artifact,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.fail_run",
        fake_fail,
    )

    with pytest.raises(RuntimeError, match="db unavailable"):
        await run_artifact_review(
            note_id="note:self",
            project_id="project:xyz",
            run_id="artifact_review_run:1",
        )

    assert fail_called["n"] == 1
    assert fake_run.status == "failed"


@pytest.mark.asyncio
async def test_run_artifact_review_rejects_mismatched_ids(monkeypatch):
    fake_run = _FakeRun(
        "artifact_review_run:1",
        note_id="note:other",
        project_id="project:xyz",
    )
    artifact = SimpleNamespace(id="note:self", content="The budget is $1M.")

    async def fake_get_run(run_id: str) -> _FakeRun:
        return fake_run

    async def fake_get_artifact(note_id: str) -> Any:
        return artifact

    async def fake_fail(*, run_id: str, error_message: str) -> _FakeRun:
        fake_run.status = "failed"
        fake_run.error_message = error_message
        return fake_run

    monkeypatch.setattr(
        "construction_os.services.artifact_review.ArtifactReviewRun.get",
        fake_get_run,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.ProjectArtifact.get",
        fake_get_artifact,
    )
    monkeypatch.setattr(
        "construction_os.services.artifact_review.fail_run",
        fake_fail,
    )

    with pytest.raises(InvalidInputError, match="note_id"):
        await run_artifact_review(
            note_id="note:self",
            project_id="project:xyz",
            run_id="artifact_review_run:1",
        )

    assert fake_run.status == "failed"
