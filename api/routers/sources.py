import json
import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse, Response
from loguru import logger
from surreal_commands import get_command_status

from api.command_service import CommandService
from api.models import (
    AssetModel,
    IngestTextSourceRequest,
    SourceCreate,
    SourceListResponse,
    SourceResponse,
    SourceStatusResponse,
    SourceUpdate,
)
from api.upload_utils import generate_unique_filename, save_uploaded_file  # noqa: F401
from commands.source_commands import SourceProcessingInput
from construction_os.config import UPLOADS_FOLDER
from construction_os.database.repository import ensure_record_id, repo_query
from construction_os.domain.project import Asset, Project, Source
from construction_os.exceptions import InvalidInputError, NotFoundError
from construction_os.knowledge.pipeline import (
    ACTIVE_PIPELINE_STAGES,
    PIPELINE_EXTRACTING,
    fetched_command_status,
    heal_pipeline_stage_if_needed,
    pipeline_processing_info,
    resolve_processing_failures,
    resolve_pipeline_status,
)
from construction_os.services.source_create import create_and_process_source
from construction_os.services.source_list import list_sources_enriched

router = APIRouter()

# Re-export upload helpers for tests that patch api.routers.sources.save_uploaded_file
__all__ = [
    "generate_unique_filename",
    "save_uploaded_file",
    "router",
]


def parse_source_form_data(
    type: str = Form(...),
    project_id: Optional[str] = Form(None),
    projects: Optional[str] = Form(None),  # JSON string of Project IDs
    url: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    artifacts: Optional[str] = Form(None),  # JSON string of Artifact IDs
    embed: str = Form("false"),  # Accept as string, convert to bool
    delete_source: str = Form("false"),  # Accept as string, convert to bool
    async_processing: str = Form("false"),  # Accept as string, convert to bool
    file: Optional[UploadFile] = File(None),
) -> tuple[SourceCreate, Optional[UploadFile]]:
    """Parse form data into SourceCreate model and return upload file separately."""
    # Convert string booleans to actual booleans
    def str_to_bool(value: str) -> bool:
        return value.lower() in ("true", "1", "yes", "on")

    embed_bool = str_to_bool(embed)
    delete_source_bool = str_to_bool(delete_source)
    async_processing_bool = str_to_bool(async_processing)

    # Parse JSON strings
    projects_list = None
    if projects:
        try:
            projects_list = json.loads(projects)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in projects field: {projects}")
            raise ValueError("Invalid JSON in projects field")

    artifacts_list = []
    if artifacts:
        try:
            artifacts_list = json.loads(artifacts)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in artifacts field: {artifacts}")
            raise ValueError("Invalid JSON in artifacts field")

    # Create SourceCreate instance
    try:
        source_data = SourceCreate(
            type=type,
            project_id=project_id,
            projects=projects_list,
            url=url,
            content=content,
            title=title,
            file_path=None,  # Will be set later if file is uploaded
            artifacts=[],  # ignored
            embed=embed_bool,
            delete_source=delete_source_bool,
            async_processing=async_processing_bool,
        )
        pass  # SourceCreate instance created successfully
    except Exception as e:
        logger.error(f"Failed to create SourceCreate instance: {e}")
        raise

    return source_data, file


@router.get("/sources", response_model=List[SourceListResponse])
async def get_sources(
    project_id: Optional[str] = Query(None, description="Filter by Project ID"),
    limit: int = Query(
        50, ge=1, le=100, description="Number of sources to return (1-100)"
    ),
    offset: int = Query(0, ge=0, description="Number of sources to skip"),
    sort_by: str = Query(
        "updated", description="Field to sort by (created or updated)"
    ),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
):
    """Get sources with pagination and sorting support."""
    try:
        rows = await list_sources_enriched(
            project_id=project_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        response_list = []
        for row in rows:
            asset = row.get("asset")
            response_list.append(
                SourceListResponse(
                    id=row["id"],
                    title=row.get("title"),
                    topics=row.get("topics") or [],
                    asset=AssetModel(
                        file_path=asset.get("file_path") if asset else None,
                        url=asset.get("url") if asset else None,
                    )
                    if asset
                    else None,
                    embedded=row.get("embedded", False),
                    embedded_chunks=0,
                    created=str(row["created"]),
                    updated=str(row["updated"]),
                    command_id=row.get("command_id"),
                    status=row.get("status"),
                    processing_info=row.get("processing_info"),
                    pipeline_stage=row.get("pipeline_stage"),
                    stage=row.get("stage"),
                    kg_status=row.get("kg_status"),
                    knowledge_graph=bool(row.get("knowledge_graph")),
                    drawing_status=row.get("drawing_status"),
                    processing_failures=row.get("processing_failures"),
                    failure_details_unavailable=row.get(
                        "failure_details_unavailable"
                    ),
                )
            )
        return response_list
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching sources: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching sources: {str(e)}")


@router.post("/sources", response_model=SourceResponse)
async def create_source(
    form_data: tuple[SourceCreate, Optional[UploadFile]] = Depends(
        parse_source_form_data
    ),
):
    """Create a new source with support for both JSON and multipart form data."""
    source_data, upload_file = form_data
    file_path = None

    try:
        if upload_file and source_data.type == "upload":
            try:
                file_path = await save_uploaded_file(upload_file)
            except Exception as e:
                logger.error(f"File upload failed: {e}")
                raise HTTPException(
                    status_code=400, detail=f"File upload failed: {str(e)}"
                )

        final_file_path = file_path or source_data.file_path
        result = await create_and_process_source(
            source_type=source_data.type,  # type: ignore[arg-type]
            title=source_data.title,
            projects=source_data.projects,
            url=source_data.url,
            content=source_data.content,
            file_path=final_file_path,
            delete_source=bool(source_data.delete_source),
            async_processing=bool(source_data.async_processing),
        )
        source = result.source

        if result.async_queued:
            return SourceResponse(
                id=source.id or "",
                title=source.title,
                topics=source.topics or [],
                asset=None,
                full_text=None,
                embedded=False,
                embedded_chunks=0,
                created=str(source.created),
                updated=str(source.updated),
                command_id=result.command_id,
                status="new",
                processing_info={"async": True, "queued": True},
            )

        embedded_chunks = await source.get_embedded_chunks()
        return SourceResponse(
            id=source.id or "",
            title=source.title,
            topics=source.topics or [],
            asset=AssetModel(
                file_path=source.asset.file_path if source.asset else None,
                url=source.asset.url if source.asset else None,
            )
            if source.asset
            else None,
            full_text=source.full_text,
            embedded=embedded_chunks > 0,
            embedded_chunks=embedded_chunks,
            created=str(source.created),
            updated=str(source.updated),
        )

    except HTTPException:
        if file_path and upload_file:
            try:
                os.unlink(file_path)
            except Exception:
                pass
        raise
    except NotFoundError as e:
        if file_path and upload_file:
            try:
                os.unlink(file_path)
            except Exception:
                pass
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidInputError as e:
        if file_path and upload_file:
            try:
                os.unlink(file_path)
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating source: {str(e)}")
        if file_path and upload_file:
            try:
                os.unlink(file_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Error creating source: {str(e)}")


@router.post("/sources/json", response_model=SourceResponse)
async def create_source_json(source_data: SourceCreate):
    """Create a new source using JSON payload (legacy endpoint for backward compatibility)."""
    # Convert to form data format and call main endpoint
    form_data = (source_data, None)
    return await create_source(form_data)


@router.post("/sources/ingest-text", response_model=SourceResponse)
async def ingest_text_source(request: IngestTextSourceRequest):
    """Ingest pre-extracted text as a searchable source (promotion fast path)."""
    from api.promotion_service import promote_text_to_source

    try:
        return await promote_text_to_source(
            content=request.content,
            title=request.title,
            project_ids=request.project_ids,
            embed=request.embed,
            artifact_ids=request.artifacts or [],
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error ingesting text source: {e}")
        raise HTTPException(status_code=500, detail=f"Error ingesting text source: {e}")


async def _resolve_source_file(source_id: str) -> tuple[str, str]:
    source = await Source.get(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    file_path = source.asset.file_path if source.asset else None
    if not file_path:
        raise HTTPException(status_code=404, detail="Source has no file to download")

    safe_root = os.path.realpath(UPLOADS_FOLDER)
    resolved_path = os.path.realpath(file_path)

    if not resolved_path.startswith(safe_root):
        logger.warning(
            f"Blocked download outside uploads directory for source {source_id}: {resolved_path}"
        )
        raise HTTPException(status_code=403, detail="Access to file denied")

    if not os.path.exists(resolved_path):
        raise HTTPException(status_code=404, detail="File not found on server")

    filename = os.path.basename(resolved_path)
    return resolved_path, filename


def _is_source_file_available(source: Source) -> Optional[bool]:
    if not source or not source.asset or not source.asset.file_path:
        return None

    file_path = source.asset.file_path
    safe_root = os.path.realpath(UPLOADS_FOLDER)
    resolved_path = os.path.realpath(file_path)

    if not resolved_path.startswith(safe_root):
        return False

    return os.path.exists(resolved_path)


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(source_id: str):
    """Get a specific source by ID."""
    try:
        source = await Source.get(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        # Get status information if command exists
        status = None
        processing_info = None
        if source.command:
            try:
                status = await source.get_status()
                processing_info = await source.get_processing_progress()
            except Exception as e:
                logger.warning(f"Failed to get status for source {source_id}: {e}")
                status = "unknown"

        embedded_chunks = await source.get_embedded_chunks()
        embed_command, _ = await _child_command_details(
            getattr(source, "embed_command", None)
        )
        kg_command, _ = await _child_command_details(
            getattr(source, "kg_command", None)
        )
        processing_failures = resolve_processing_failures(
            getattr(source, "processing_failures", None),
            embed_command=embed_command,
            kg_command=kg_command,
            kg_run=await _latest_kg_run(str(source.id or source_id)),
        )
        pipeline_stage = getattr(source, "pipeline_stage", None)

        # Get associated projects
        projects_query = await repo_query(
            "SELECT VALUE out FROM reference WHERE in = $source_id",
            {"source_id": ensure_record_id(source.id or source_id)},
        )
        project_ids = (
            [str(pid) for pid in projects_query] if projects_query else []
        )

        return SourceResponse(
            id=source.id or "",
            title=source.title,
            topics=source.topics or [],
            asset=AssetModel(
                file_path=source.asset.file_path if source.asset else None,
                url=source.asset.url if source.asset else None,
            )
            if source.asset
            else None,
            full_text=source.full_text,
            embedded=embedded_chunks > 0,
            embedded_chunks=embedded_chunks,
            file_available=_is_source_file_available(source),
            created=str(source.created),
            updated=str(source.updated),
            # Status fields
            command_id=str(source.command) if source.command else None,
            status=status,
            processing_info=processing_info,
            pipeline_stage=pipeline_stage,
            stage=pipeline_stage,
            processing_failures=processing_failures,
            failure_details_unavailable=(
                pipeline_stage == "failed" and not processing_failures
            ),
            # Project associations
            projects=project_ids,
        )
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Source not found")
    except Exception as e:
        logger.error(f"Error fetching source {source_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching source: {str(e)}")


@router.head("/sources/{source_id}/download")
async def check_source_file(source_id: str):
    """Check if a source has a downloadable file."""
    try:
        await _resolve_source_file(source_id)
        return Response(status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking file for source {source_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify file")


@router.get("/sources/{source_id}/download")
async def download_source_file(source_id: str):
    """Download the original file associated with an uploaded source."""
    try:
        resolved_path, filename = await _resolve_source_file(source_id)
        return FileResponse(
            path=resolved_path,
            filename=filename,
            media_type="application/octet-stream",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file for source {source_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to download source file")


async def _child_command_details(
    command_ref: Any,
) -> Tuple[Optional[dict[str, Any]], bool]:
    """Resolve status and failure output for an embed/KG command link."""
    if not command_ref:
        return None, False
    try:
        status_result = await get_command_status(str(command_ref))
        if not status_result:
            return {"id": str(command_ref), "status": "unknown"}, True
        return (
            {
                "id": str(command_ref),
                "status": status_result.status or "unknown",
                "result": getattr(status_result, "result", None),
                "error_message": getattr(status_result, "error_message", None),
                "updated": str(status_result.updated)
                if getattr(status_result, "updated", None)
                else None,
            },
            True,
        )
    except Exception as e:
        logger.warning(f"Failed to get child command status for {command_ref}: {e}")
        return {"id": str(command_ref), "status": "unknown"}, True


async def _latest_kg_run(source_id: str) -> Optional[dict[str, Any]]:
    """Fetch the latest KG run for diagnostics fallback."""
    try:
        rows = await repo_query(
            """
            SELECT status, error_message, error_type, started_at, finished_at, updated, command_id
            FROM kg_extraction_run
            WHERE source_id = $source_id
            ORDER BY started_at DESC
            LIMIT 1
            """,
            {"source_id": ensure_record_id(source_id)},
        )
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning(f"Failed to load KG diagnostics for {source_id}: {exc}")
        return None


@router.get("/sources/{source_id}/status", response_model=SourceStatusResponse)
async def get_source_status(source_id: str):
    """Get processing status for a source."""
    try:
        # First, verify source exists
        source = await Source.get(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        pipeline_stage = getattr(source, "pipeline_stage", None)
        embed_command, has_embed = await _child_command_details(
            getattr(source, "embed_command", None)
        )
        kg_command, has_kg = await _child_command_details(
            getattr(source, "kg_command", None)
        )
        embed_status, _ = fetched_command_status(embed_command)
        kg_status, _ = fetched_command_status(kg_command)
        latest_kg_run = await _latest_kg_run(str(source.id or source_id))
        knowledge_graph = bool(
            latest_kg_run and str(latest_kg_run.get("status") or "") == "completed"
        )
        if knowledge_graph:
            kg_status = "completed"
        processing_failures = resolve_processing_failures(
            getattr(source, "processing_failures", None),
            embed_command=embed_command,
            kg_command=kg_command,
            kg_run=latest_kg_run,
        )
        failure_details_unavailable = (
            pipeline_stage == "failed" and not processing_failures
        )
        # Cheap existence check — avoid COUNT on every 2s poll while embedding runs.
        try:
            emb_rows = await repo_query(
                "SELECT VALUE id FROM source_embedding WHERE source = $id LIMIT 1",
                {"id": ensure_record_id(source.id or source_id)},
            )
            embedded = bool(emb_rows)
        except Exception:
            embedded = None

        # Check if this is a legacy source (no command)
        if not source.command:
            if pipeline_stage in ACTIVE_PIPELINE_STAGES:
                status, stage, message = resolve_pipeline_status(
                    extract_status="completed",
                    pipeline_stage=pipeline_stage,
                    embed_command_status=embed_status,
                    kg_command_status=kg_status,
                    has_embed_command=has_embed,
                    has_kg_command=has_kg,
                )
                await heal_pipeline_stage_if_needed(
                    str(source.id or source_id),
                    current_stage=pipeline_stage,
                    resolved_stage=stage,
                )
                return SourceStatusResponse(
                    status=status,
                    message=message,
                    processing_info=pipeline_processing_info(None, stage),
                    command_id=None,
                    stage=stage,
                    embedded=embedded,
                    kg_status=kg_status,
                    knowledge_graph=knowledge_graph,
                    processing_failures=processing_failures,
                    failure_details_unavailable=(
                        stage == "failed" and not processing_failures
                    ),
                )
            return SourceStatusResponse(
                status=None,
                message="Legacy source (completed before async processing)",
                processing_info=None,
                command_id=None,
                stage=pipeline_stage or "completed",
                embedded=embedded,
                kg_status=kg_status,
                knowledge_graph=knowledge_graph,
                processing_failures=processing_failures,
                failure_details_unavailable=failure_details_unavailable,
            )

        # Get command status and processing info
        try:
            extract_status = await source.get_status()
            processing_info = await source.get_processing_progress()
            status, stage, message = resolve_pipeline_status(
                extract_status=extract_status,
                pipeline_stage=pipeline_stage,
                embed_command_status=embed_status,
                kg_command_status=kg_status,
                has_embed_command=has_embed,
                has_kg_command=has_kg,
            )
            await heal_pipeline_stage_if_needed(
                str(source.id or source_id),
                current_stage=pipeline_stage,
                resolved_stage=stage,
            )

            return SourceStatusResponse(
                status=status,
                message=message,
                processing_info=pipeline_processing_info(processing_info, stage),
                command_id=str(source.command) if source.command else None,
                stage=stage,
                embedded=embedded,
                kg_status=kg_status,
                knowledge_graph=knowledge_graph,
                processing_failures=processing_failures,
                failure_details_unavailable=(
                    stage == "failed" and not processing_failures
                ),
            )

        except Exception as e:
            logger.warning(f"Failed to get status for source {source_id}: {e}")
            return SourceStatusResponse(
                status="unknown",
                message="Failed to retrieve processing status",
                processing_info=None,
                command_id=str(source.command) if source.command else None,
                stage=getattr(source, "pipeline_stage", None),
                embedded=embedded,
                kg_status=kg_status,
                knowledge_graph=knowledge_graph,
                processing_failures=processing_failures,
                failure_details_unavailable=failure_details_unavailable,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching status for source {source_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching source status: {str(e)}"
        )


@router.put("/sources/{source_id}", response_model=SourceResponse)
async def update_source(source_id: str, source_update: SourceUpdate):
    """Update a source."""
    try:
        source = await Source.get(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        # Update only provided fields
        if source_update.title is not None:
            source.title = source_update.title
        if source_update.topics is not None:
            source.topics = source_update.topics

        await source.save()

        embedded_chunks = await source.get_embedded_chunks()
        return SourceResponse(
            id=source.id or "",
            title=source.title,
            topics=source.topics or [],
            asset=AssetModel(
                file_path=source.asset.file_path if source.asset else None,
                url=source.asset.url if source.asset else None,
            )
            if source.asset
            else None,
            full_text=source.full_text,
            embedded=embedded_chunks > 0,
            embedded_chunks=embedded_chunks,
            created=str(source.created),
            updated=str(source.updated),
        )
    except HTTPException:
        raise
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating source {source_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating source: {str(e)}")


@router.post("/sources/{source_id}/retry", response_model=SourceResponse)
async def retry_source_processing(source_id: str):
    """Retry processing for a failed or stuck source."""
    try:
        # First, verify source exists
        source = await Source.get(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        # Check if source already has a running command
        if source.command:
            try:
                status = await source.get_status()
                if status in ["running", "queued"]:
                    raise HTTPException(
                        status_code=400,
                        detail="Source is already processing. Cannot retry while processing is active.",
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to check current status for source {source_id}: {e}"
                )
                # Continue with retry if we can't check status

        # Get projects that this source belongs to. `reference` is a graph edge
        # (RELATE source->reference->Project), so it only has `in`/`out` columns —
        # there is no `source`/`Project` column. Mirror the working query at the
        # source-list path above. See issue #861.
        references = await repo_query(
            "SELECT VALUE out FROM reference WHERE in = $source_id",
            {"source_id": ensure_record_id(source.id or source_id)},
        )
        project_ids = [str(nb_id) for nb_id in references] if references else []

        if not project_ids:
            raise HTTPException(
                status_code=400, detail="Source is not associated with any projects"
            )

        # Prepare content_state based on source asset
        content_state = {}
        if source.asset:
            if source.asset.file_path:
                content_state = {
                    "file_path": source.asset.file_path,
                    "delete_source": False,  # Don't delete on retry
                }
            elif source.asset.url:
                content_state = {"url": source.asset.url}
            else:
                raise HTTPException(
                    status_code=400, detail="Source asset has no file_path or url"
                )
        else:
            # Check if it's a text source by trying to get full_text
            if source.full_text:
                content_state = {"content": source.full_text}
            else:
                raise HTTPException(
                    status_code=400, detail="Cannot determine source content for retry"
                )

        try:
            # Import command modules to ensure they're registered
            import commands.source_commands  # noqa: F401

            # Submit new command for background processing
            command_input = SourceProcessingInput(
                source_id=str(source.id),
                content_state=content_state,
                project_ids=project_ids,
                artifacts=[],  # No artifacts on retry unless user re-applies manually
                embed=True,  # Always embed on retry
            )

            command_id = await CommandService.submit_command_job(
                "construction_os",  # app name
                "process_source",  # command name
                command_input.model_dump(),
            )

            logger.info(
                f"Submitted retry processing command: {command_id} for source {source_id}"
            )

            # Update source with new command ID and reset pipeline child jobs
            # command_id already includes 'command:' prefix
            source.command = ensure_record_id(command_id)
            source.embed_command = None
            source.kg_command = None
            source.pipeline_stage = PIPELINE_EXTRACTING
            await source.save()

            # Get current embedded chunks count
            embedded_chunks = await source.get_embedded_chunks()

            # Return updated source response
            return SourceResponse(
                id=source.id or "",
                title=source.title,
                topics=source.topics or [],
                asset=AssetModel(
                    file_path=source.asset.file_path if source.asset else None,
                    url=source.asset.url if source.asset else None,
                )
                if source.asset
                else None,
                full_text=source.full_text,
                embedded=embedded_chunks > 0,
                embedded_chunks=embedded_chunks,
                created=str(source.created),
                updated=str(source.updated),
                command_id=command_id,
                status="queued",
                processing_info={
                    "retry": True,
                    "queued": True,
                    "stage": PIPELINE_EXTRACTING,
                },
                pipeline_stage=PIPELINE_EXTRACTING,
                stage=PIPELINE_EXTRACTING,
                processing_failures=resolve_processing_failures(
                    getattr(source, "processing_failures", None)
                ),
            )

        except Exception as e:
            logger.error(
                f"Failed to submit retry processing command for source {source_id}: {e}"
            )
            raise HTTPException(
                status_code=500, detail=f"Failed to queue retry processing: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying source processing for {source_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error retrying source processing: {str(e)}"
        )


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str):
    """Delete a source."""
    try:
        source = await Source.get(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        await source.delete()

        return {"message": "Source deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting source {source_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting source: {str(e)}")


