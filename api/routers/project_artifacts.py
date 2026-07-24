"""Project Artifacts API — persisted project outputs (canonical routes)."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from loguru import logger

from api.models import (
    ArtifactReviewApplyRequest,
    ArtifactReviewApplyResponse,
    ArtifactReviewRunResponse,
    ArtifactReviewStartResponse,
    ProjectArtifactCreate,
    ProjectArtifactResponse,
    ProjectArtifactUpdate,
    PromoteToSourceRequest,
    SourceResponse,
)
from construction_os.database.repository import ensure_record_id
from construction_os.domain.artifact_review import ArtifactReviewRun, get_latest_run
from construction_os.domain.project import Project
from construction_os.domain.project_artifact import (
    PDF_EXPORT_KINDS,
    ProjectArtifact,
    resolve_kind_from_payload,
)
from construction_os.exceptions import InvalidInputError, NotFoundError
from construction_os.services.artifact_review import (
    apply_review_fixes,
    is_run_stale,
    start_artifact_review,
)
from construction_os.services.project_artifacts import (
    create_project_artifact,
    project_artifact_to_dict,
)
from construction_os.utils.note_pdf_export import export_pdf_filename, render_note_pdf

router = APIRouter()


def _to_response(
    artifact: ProjectArtifact, command_id: Optional[str] = None
) -> ProjectArtifactResponse:
    data = project_artifact_to_dict(artifact, command_id)
    return ProjectArtifactResponse(
        id=data["id"],
        title=data["title"],
        content=data["content"],
        artifact_kind=data["artifact_kind"],
        note_type=data["note_type"],
        created=data["created"] or "",
        updated=data["updated"] or "",
        command_id=data.get("command_id"),
    )


def _review_to_response(
    run: ArtifactReviewRun, content: str
) -> ArtifactReviewRunResponse:
    return ArtifactReviewRunResponse(
        id=str(run.id),
        note_id=str(run.note_id),
        project_id=str(run.project_id),
        status=run.status,
        command_id=str(run.command_id) if run.command_id is not None else None,
        findings=run.findings,
        summary=run.summary,
        content_hash=run.content_hash,
        error_message=run.error_message,
        started_at=str(run.started_at) if run.started_at is not None else None,
        finished_at=str(run.finished_at) if run.finished_at is not None else None,
        stale=is_run_stale(run, content),
    )


@router.get("/project-artifacts", response_model=List[ProjectArtifactResponse])
async def list_project_artifacts(
    project_id: Optional[str] = Query(None, description="Filter by Project ID"),
):
    """List project artifacts with optional project filtering."""
    try:
        if project_id:
            project = await Project.get(project_id)
            artifacts = await project.get_artifacts()
        else:
            artifacts = await ProjectArtifact.get_all(order_by="updated desc")

        return [_to_response(a) for a in artifacts]
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except Exception as e:
        logger.error(f"Error fetching project artifacts: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching project artifacts: {str(e)}"
        )


@router.post("/project-artifacts", response_model=ProjectArtifactResponse)
async def create_project_artifact_endpoint(payload: ProjectArtifactCreate):
    """Create a new project artifact."""
    try:
        result = await create_project_artifact(
            content=payload.content or "",
            project_id=payload.project_id,
            title=payload.title,
            artifact_kind=payload.artifact_kind,
            note_type=payload.note_type,
        )
        return ProjectArtifactResponse(
            id=result["id"],
            title=result["title"],
            content=result["content"],
            artifact_kind=result["artifact_kind"],
            note_type=result["note_type"],
            created=result["created"] or "",
            updated=result["updated"] or "",
            command_id=result.get("command_id"),
        )
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating project artifact: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error creating project artifact: {str(e)}"
        )


@router.get(
    "/project-artifacts/{artifact_id}", response_model=ProjectArtifactResponse
)
async def get_project_artifact(artifact_id: str):
    """Get a specific project artifact by ID."""
    try:
        artifact = await ProjectArtifact.get(artifact_id)
        return _to_response(artifact)
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Project artifact not found")
    except Exception as e:
        logger.error(f"Error fetching project artifact {artifact_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching project artifact: {str(e)}"
        )


@router.put(
    "/project-artifacts/{artifact_id}", response_model=ProjectArtifactResponse
)
async def update_project_artifact(
    artifact_id: str, payload: ProjectArtifactUpdate
):
    """Update a project artifact."""
    try:
        artifact = await ProjectArtifact.get(artifact_id)

        if payload.title is not None:
            artifact.title = payload.title
        if payload.content is not None:
            artifact.content = payload.content
        if payload.artifact_kind is not None or payload.note_type is not None:
            artifact.note_type = resolve_kind_from_payload(
                artifact_kind=payload.artifact_kind,
                note_type=payload.note_type,
                default=None,
            )

        command_id = await artifact.save()
        return _to_response(artifact, command_id)
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Project artifact not found")
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating project artifact {artifact_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating project artifact: {str(e)}"
        )


@router.post(
    "/project-artifacts/{artifact_id}/ingest-as-source",
    response_model=SourceResponse,
)
async def ingest_project_artifact_as_source(
    artifact_id: str, request: PromoteToSourceRequest
):
    """Promote a generated or AI artifact into an ingested text source."""
    from api.promotion_service import promote_note_to_source

    try:
        return await promote_note_to_source(
            artifact_id,
            project_id=request.project_id,
            embed=request.embed,
            artifact_ids=request.artifacts or [],
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error ingesting project artifact {artifact_id} as source: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error ingesting artifact as source: {e}"
        )


@router.get("/project-artifacts/{artifact_id}/export/pdf")
async def export_project_artifact_pdf(artifact_id: str):
    """Export a generated project artifact as a formatted PDF."""
    try:
        artifact = await ProjectArtifact.get(artifact_id)
        if artifact.artifact_kind not in PDF_EXPORT_KINDS:
            raise InvalidInputError(
                "Only generated project artifacts can be exported as PDF"
            )

        pdf_bytes = render_note_pdf(
            title=artifact.title or "Artifact",
            content=artifact.content or "",
            updated=str(artifact.updated) if artifact.updated else None,
        )
        filename = export_pdf_filename(artifact.title)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Project artifact not found")
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error exporting project artifact {artifact_id} as PDF: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error exporting artifact as PDF: {str(e)}"
        )


@router.post(
    "/project-artifacts/{note_id}/review",
    response_model=ArtifactReviewStartResponse,
)
async def start_project_artifact_review(note_id: str):
    """Start an async factual review for a project artifact."""
    try:
        run, command_id = await start_artifact_review(note_id)
        return ArtifactReviewStartResponse(
            run_id=str(run.id),
            command_id=command_id,
            status=run.status,
        )
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting artifact review for {note_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error starting artifact review: {str(e)}"
        )


@router.get(
    "/project-artifacts/{note_id}/review",
    response_model=ArtifactReviewRunResponse,
)
async def get_latest_project_artifact_review(note_id: str):
    """Get the latest factual review run for a project artifact."""
    try:
        artifact = await ProjectArtifact.get(note_id)
        run = await get_latest_run(note_id)
        if run is None:
            raise HTTPException(status_code=404, detail="No review run found")
        return _review_to_response(run, artifact.content or "")
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")
    except Exception as e:
        logger.error(f"Error fetching latest artifact review for {note_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching artifact review: {str(e)}"
        )


@router.get(
    "/project-artifacts/{note_id}/review/{run_id}",
    response_model=ArtifactReviewRunResponse,
)
async def get_project_artifact_review(note_id: str, run_id: str):
    """Get a specific factual review run for a project artifact."""
    try:
        artifact = await ProjectArtifact.get(note_id)
        try:
            run = await ArtifactReviewRun.get(run_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="Review run not found") from exc
        if str(ensure_record_id(run.note_id)) != str(ensure_record_id(note_id)):
            raise HTTPException(status_code=404, detail="Review run not found")
        return _review_to_response(run, artifact.content or "")
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")
    except Exception as e:
        logger.error(
            f"Error fetching artifact review {run_id} for {note_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=500, detail=f"Error fetching artifact review: {str(e)}"
        )


@router.post(
    "/project-artifacts/{note_id}/review/apply",
    response_model=ArtifactReviewApplyResponse,
)
async def apply_project_artifact_review_fixes(
    note_id: str, payload: ArtifactReviewApplyRequest
):
    """Apply suggested fixes from a review run to the artifact content."""
    try:
        artifact, skipped = await apply_review_fixes(
            note_id=note_id,
            run_id=payload.run_id,
            finding_ids=payload.finding_ids,
        )
        return ArtifactReviewApplyResponse(
            artifact=_to_response(artifact),
            skipped_spans=skipped,
        )
    except HTTPException:
        raise
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidInputError as e:
        if "stale" in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error applying artifact review fixes for {note_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error applying artifact review fixes: {str(e)}"
        )


@router.delete("/project-artifacts/{artifact_id}")
async def delete_project_artifact(artifact_id: str):
    """Delete a project artifact."""
    try:
        artifact = await ProjectArtifact.get(artifact_id)
        await artifact.delete()
        return {"message": "Project artifact deleted successfully"}
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Project artifact not found")
    except Exception as e:
        logger.error(f"Error deleting project artifact {artifact_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error deleting project artifact: {str(e)}"
        )
