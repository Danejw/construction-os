"""Artifact factual review run domain model and repository helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, Literal, Optional

from construction_os.database.repository import ensure_record_id, repo_query
from construction_os.domain.base import ObjectModel
from construction_os.exceptions import NotFoundError

ReviewRunStatus = Literal[
    "pending", "running", "passed", "needs_review", "failed"
]

CompleteRunStatus = Literal["passed", "needs_review"]


class ArtifactReviewRun(ObjectModel):
    table_name: ClassVar[str] = "artifact_review_run"
    note_id: str
    project_id: str
    status: ReviewRunStatus = "pending"
    command_id: Optional[str] = None
    findings: Optional[Dict[str, Any]] = None
    summary: Optional[Dict[str, Any]] = None
    content_hash: str
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    nullable_fields: ClassVar[set[str]] = {
        "command_id",
        "findings",
        "summary",
        "error_message",
        "started_at",
        "finished_at",
    }

    def _prepare_save_data(self) -> Dict[str, Any]:
        data = super()._prepare_save_data()
        for field in ("note_id", "project_id"):
            if field in data and data[field] is not None:
                data[field] = ensure_record_id(data[field])
        return data


async def get_latest_run(note_id: str) -> Optional[ArtifactReviewRun]:
    rows = await repo_query(
        """
        SELECT * FROM artifact_review_run
        WHERE note_id = $note_id
        ORDER BY started_at DESC, created DESC
        LIMIT 1
        """,
        {"note_id": ensure_record_id(note_id)},
    )
    if not rows:
        return None
    return ArtifactReviewRun(**rows[0])


async def get_run(run_id: str) -> Optional[ArtifactReviewRun]:
    try:
        return await ArtifactReviewRun.get(run_id)
    except NotFoundError:
        return None


async def create_pending_run(
    *,
    note_id: str,
    project_id: str,
    content_hash: str,
) -> ArtifactReviewRun:
    run = ArtifactReviewRun(
        note_id=note_id,
        project_id=project_id,
        status="pending",
        content_hash=content_hash,
        started_at=datetime.now(timezone.utc),
    )
    await run.save()
    return run


async def mark_run_running(run_id: str) -> ArtifactReviewRun:
    run = await ArtifactReviewRun.get(run_id)
    run.status = "running"
    await run.save()
    return run


async def complete_run(
    *,
    run_id: str,
    status: CompleteRunStatus,
    findings: Dict[str, Any],
    summary: Dict[str, Any],
) -> ArtifactReviewRun:
    run = await ArtifactReviewRun.get(run_id)
    run.status = status
    run.findings = findings
    run.summary = summary
    run.finished_at = datetime.now(timezone.utc)
    await run.save()
    return run


async def fail_run(*, run_id: str, error_message: str) -> ArtifactReviewRun:
    run = await ArtifactReviewRun.get(run_id)
    run.status = "failed"
    run.error_message = error_message
    run.finished_at = datetime.now(timezone.utc)
    await run.save()
    return run
