# construction_os/services/artifact_review.py
"""Artifact factual review helpers and orchestration."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Literal, Optional, Sequence

from ai_prompter import Prompter
from loguru import logger
from pydantic import BaseModel, Field
from surreal_commands import submit_command

from construction_os.ai.structured import invoke_structured
from construction_os.database.repository import ensure_record_id, repo_query
from construction_os.domain.artifact_review import (
    ArtifactReviewRun,
    complete_run,
    create_pending_run,
    fail_run,
    mark_run_running,
)
from construction_os.domain.project_artifact import ProjectArtifact
from construction_os.exceptions import InvalidInputError, NotFoundError
from construction_os.retrieval.evidence_retriever import retrieve
from construction_os.retrieval.types import EvidenceItem
from construction_os.services.project_memory import get_project_memory

ReviewAggregateStatus = Literal["passed", "needs_review"]

SourceVerdict = Literal[
    "supported", "unsupported", "contradicted", "not_in_corpus", "opinion"
]
MemoryVerdict = Literal["memory_aligned", "memory_conflict", "memory_novel"]

CLAIM_CAP = 40
JUDGE_BATCH_SIZE = 8
EVIDENCE_PER_CLAIM = 6
EVIDENCE_EXCERPT_CHARS = 1500

_NEEDS_REVIEW_SOURCE = frozenset({"unsupported", "contradicted"})
_NEEDS_REVIEW_MEMORY = frozenset({"memory_conflict"})


class ClaimSegment(BaseModel):
    finding_id: str
    claim_text: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    is_opinion: bool = False


class SegmentResult(BaseModel):
    claims: list[ClaimSegment] = Field(default_factory=list)


class ClaimFinding(BaseModel):
    finding_id: str
    claim_text: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    source_verdict: SourceVerdict
    confidence: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
    suggested_fix: Optional[str] = None
    claim_span: Optional[str] = None


class MemoryFinding(BaseModel):
    finding_id: str
    claim_text: Optional[str] = None
    memory_verdict: MemoryVerdict
    fact_id: Optional[str] = None
    rationale: str = ""
    suggested_fix: Optional[str] = None


class ReviewReport(BaseModel):
    claims: list[ClaimFinding] = Field(default_factory=list)
    memory_findings: list[MemoryFinding] = Field(default_factory=list)
    truncated: bool = False
    notes: Optional[str] = None


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


def is_run_stale(run: ArtifactReviewRun, content: str) -> bool:
    return run.content_hash != content_hash(content or "")


def _evidence_text(item: EvidenceItem) -> str:
    content = item.content
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def _format_evidence_excerpts(items: Sequence[EvidenceItem]) -> str:
    if not items:
        return "(no evidence)"
    parts: list[str] = []
    for item in items:
        excerpt = _evidence_text(item)[:EVIDENCE_EXCERPT_CHARS]
        parts.append(
            f"- id={item.id} parent_id={item.parent_id or ''} "
            f"title={item.title or ''}\n  {excerpt}"
        )
    return "\n".join(parts)


def _active_memory_facts_payload(snapshot: Any) -> list[dict[str, Any]]:
    if snapshot is None:
        return []
    facts = getattr(snapshot, "facts", None) or []
    payload: list[dict[str, Any]] = []
    for fact in facts:
        if getattr(fact, "status", None) != "active":
            continue
        payload.append(
            {
                "fact_id": fact.fact_id,
                "category": fact.category,
                "subject": fact.subject,
                "value": fact.value,
                "status": fact.status,
            }
        )
    return payload


def _build_summary(report: ReviewReport) -> dict[str, Any]:
    source_counts = Counter(c.source_verdict for c in report.claims)
    memory_counts = Counter(m.memory_verdict for m in report.memory_findings)
    return {
        "source_verdicts": dict(source_counts),
        "memory_verdicts": dict(memory_counts),
        "claim_count": len(report.claims),
        "memory_finding_count": len(report.memory_findings),
        "truncated": report.truncated,
    }


def _merge_reports(
    parts: Sequence[ReviewReport], *, truncated: bool
) -> ReviewReport:
    """Merge batch reports; namespace memory finding_ids per batch to avoid collisions."""
    claims: list[ClaimFinding] = []
    memory_findings: list[MemoryFinding] = []
    notes_parts: list[str] = []
    seen_claim_ids: set[str] = set()
    seen_memory_ids: set[str] = set()
    for batch_idx, part in enumerate(parts):
        for claim in part.claims:
            if claim.finding_id in seen_claim_ids:
                continue
            seen_claim_ids.add(claim.finding_id)
            claims.append(claim)
        for memory in part.memory_findings:
            # Judge batches often reuse ids like memory_1; namespace so later
            # batches do not drop distinct findings (e.g. memory_conflict).
            namespaced_id = f"b{batch_idx}:{memory.finding_id}"
            if namespaced_id in seen_memory_ids:
                continue
            seen_memory_ids.add(namespaced_id)
            memory_findings.append(
                memory.model_copy(update={"finding_id": namespaced_id})
            )
        if part.notes:
            notes_parts.append(part.notes)
    return ReviewReport(
        claims=claims,
        memory_findings=memory_findings,
        truncated=truncated,
        notes="\n".join(notes_parts) if notes_parts else None,
    )


def _chunk_claims(
    claims: Sequence[ClaimSegment], size: int
) -> list[list[ClaimSegment]]:
    if size <= 0:
        return [list(claims)]
    return [list(claims[i : i + size]) for i in range(0, len(claims), size)]


async def resolve_project_id_for_note(note_id: str) -> str:
    rows = await repo_query(
        "SELECT VALUE out FROM project_note WHERE in = $note_id",
        {"note_id": ensure_record_id(note_id)},
    )
    if not rows:
        raise InvalidInputError("Artifact is not linked to a project")
    return str(rows[0])


async def _segment_claims(
    *, content: str, model_id: Optional[str]
) -> SegmentResult:
    prompt = Prompter(prompt_template="artifact_review/segment").render(
        data={"artifact_content": content}
    )
    return await invoke_structured(
        prompt,
        SegmentResult,
        model_id=model_id,
        default_type="tools",
        max_tokens=4000,
    )


async def _retrieve_for_claim(
    *, claim: ClaimSegment, project_id: str, note_id: str
) -> list[EvidenceItem]:
    if claim.is_opinion or not (claim.claim_text or "").strip():
        return []
    bundle = await retrieve(
        claim.claim_text,
        project_id=project_id,
        mode="auto",
        limit=EVIDENCE_PER_CLAIM,
    )
    return exclude_self_evidence(bundle.items, note_id)


async def _judge_batch(
    *,
    content: str,
    claims: Sequence[ClaimSegment],
    evidence_by_finding: dict[str, list[EvidenceItem]],
    memory_facts: Sequence[dict[str, Any]],
    model_id: Optional[str],
) -> ReviewReport:
    claims_payload = [c.model_dump() for c in claims]
    evidence_blocks: list[str] = []
    for claim in claims:
        excerpts = _format_evidence_excerpts(
            evidence_by_finding.get(claim.finding_id, [])
        )
        evidence_blocks.append(
            f"### Claim {claim.finding_id}\n{excerpts}"
        )
    prompt = Prompter(prompt_template="artifact_review/judge").render(
        data={
            "artifact_content": content,
            "claims_json": json.dumps(claims_payload, ensure_ascii=False),
            "evidence_excerpts": "\n\n".join(evidence_blocks),
            "memory_facts_json": json.dumps(list(memory_facts), ensure_ascii=False),
        }
    )
    return await invoke_structured(
        prompt,
        ReviewReport,
        model_id=model_id,
        default_type="tools",
        max_tokens=4000,
    )


async def _fail_run_safe(*, run_id: str, error_message: str) -> None:
    """Mark a run failed without masking the original error if fail_run itself fails."""
    try:
        await fail_run(run_id=run_id, error_message=error_message)
    except Exception as fail_exc:
        logger.exception(
            "Could not mark artifact review run {} as failed: {}", run_id, fail_exc
        )


async def run_artifact_review(
    *,
    note_id: str,
    project_id: str,
    run_id: str,
    model_id: Optional[str] = None,
) -> ArtifactReviewRun:
    """Segment, retrieve, judge, and persist a factual review run."""
    try:
        run = await ArtifactReviewRun.get(run_id)
        artifact = await ProjectArtifact.get(note_id)

        if str(ensure_record_id(run.note_id)) != str(ensure_record_id(note_id)):
            raise InvalidInputError(
                "Review run note_id does not match the requested artifact"
            )
        if str(ensure_record_id(run.project_id)) != str(ensure_record_id(project_id)):
            raise InvalidInputError(
                "Review run project_id does not match the requested project"
            )

        content = (artifact.content or "").strip()
        if not content:
            raise ValueError("Artifact content cannot be empty")

        await mark_run_running(run_id)

        segment = await _segment_claims(content=content, model_id=model_id)
        claims = list(segment.claims)
        truncated = len(claims) > CLAIM_CAP
        if truncated:
            claims = claims[:CLAIM_CAP]

        if not claims:
            report = ReviewReport(claims=[], memory_findings=[], truncated=False)
            return await complete_run(
                run_id=run_id,
                status="passed",
                findings=report.model_dump(),
                summary=_build_summary(report),
            )

        snapshot = await get_project_memory(project_id)
        memory_facts = _active_memory_facts_payload(snapshot)

        batch_reports: list[ReviewReport] = []
        for batch in _chunk_claims(claims, JUDGE_BATCH_SIZE):
            evidence_by_finding: dict[str, list[EvidenceItem]] = {}
            for claim in batch:
                evidence_by_finding[claim.finding_id] = await _retrieve_for_claim(
                    claim=claim,
                    project_id=project_id,
                    note_id=note_id,
                )
            batch_reports.append(
                await _judge_batch(
                    content=content,
                    claims=batch,
                    evidence_by_finding=evidence_by_finding,
                    memory_facts=memory_facts,
                    model_id=model_id,
                )
            )

        report = _merge_reports(batch_reports, truncated=truncated)
        status = aggregate_review_status(
            source_verdicts=[c.source_verdict for c in report.claims],
            memory_verdicts=[m.memory_verdict for m in report.memory_findings],
        )
        return await complete_run(
            run_id=run_id,
            status=status,
            findings=report.model_dump(),
            summary=_build_summary(report),
        )
    except ValueError as exc:
        logger.error("Artifact review permanent failure for {}: {}", run_id, exc)
        await _fail_run_safe(run_id=run_id, error_message=str(exc))
        raise
    except InvalidInputError as exc:
        logger.error("Artifact review invalid input for {}: {}", run_id, exc)
        await _fail_run_safe(run_id=run_id, error_message=str(exc))
        raise
    except Exception as exc:
        logger.exception("Artifact review failed for {}: {}", run_id, exc)
        await _fail_run_safe(run_id=run_id, error_message=str(exc))
        raise


async def start_artifact_review(note_id: str) -> tuple[ArtifactReviewRun, str]:
    try:
        artifact = await ProjectArtifact.get(note_id)
    except NotFoundError as exc:
        raise NotFoundError("Artifact not found") from exc

    if not (artifact.content or "").strip():
        raise InvalidInputError("Artifact content cannot be empty")

    project_id = await resolve_project_id_for_note(note_id)
    run = await create_pending_run(
        note_id=str(artifact.id),
        project_id=project_id,
        content_hash=content_hash(artifact.content or ""),
    )
    command_id = str(
        submit_command(
            "construction_os",
            "review_artifact",
            {
                "note_id": str(artifact.id),
                "project_id": project_id,
                "run_id": str(run.id),
            },
        )
    )
    run.command_id = command_id
    await run.save()
    return run, command_id


async def apply_review_fixes(
    *, note_id: str, run_id: str, finding_ids: list[str]
) -> tuple[ProjectArtifact, list[str]]:
    try:
        artifact = await ProjectArtifact.get(note_id)
    except NotFoundError as exc:
        raise NotFoundError("Artifact not found") from exc

    try:
        run = await ArtifactReviewRun.get(run_id)
    except NotFoundError as exc:
        raise NotFoundError("Review run not found") from exc

    if str(ensure_record_id(run.note_id)) != str(ensure_record_id(note_id)):
        raise NotFoundError("Review run not found")

    if is_run_stale(run, artifact.content or ""):
        raise InvalidInputError(
            "Review run is stale; re-run review before applying fixes"
        )

    report = ReviewReport.model_validate(run.findings or {})
    id_set = set(finding_ids)
    replacements: list[tuple[str, str]] = []
    for finding in report.claims:
        if finding.finding_id not in id_set:
            continue
        if finding.suggested_fix and finding.claim_span:
            replacements.append((finding.claim_span, finding.suggested_fix))
    for finding in report.memory_findings:
        if finding.finding_id not in id_set:
            continue
        if finding.suggested_fix and finding.claim_text:
            replacements.append((finding.claim_text, finding.suggested_fix))

    new_content, skipped = apply_claim_spans(artifact.content or "", replacements)
    if new_content != artifact.content:
        artifact.content = new_content
        await artifact.save()
    return artifact, skipped
