"""Enriched source listing shared by project-scoped and global list endpoints."""

from __future__ import annotations

from typing import Any, Optional

from construction_os.database.repository import ensure_record_id, repo_query
from construction_os.domain.project import Project
from construction_os.exceptions import NotFoundError
from construction_os.knowledge.pipeline import (
    fetched_command_status,
    heal_pipeline_stage_if_needed,
    pipeline_processing_info,
    resolve_processing_failures,
    resolve_pipeline_status,
)

_ENRICHED_SOURCE_FIELDS = """
id, asset, created, title, updated, topics, command,
embed_command, kg_command, pipeline_stage, processing_failures,
(SELECT status, error_message, error_type, started_at, finished_at, updated, command_id
 FROM kg_extraction_run WHERE source_id = $parent.id
 ORDER BY started_at DESC LIMIT 1)[0] AS latest_kg_run,
(SELECT VALUE id FROM source_embedding WHERE source = $parent.id LIMIT 1) != [] AS embedded,
(SELECT status, created FROM drawing_extraction_run WHERE source_id = $parent.id
 ORDER BY created DESC LIMIT 1)[0] AS latest_drawing_run
"""


async def list_sources_enriched(
    *,
    project_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "updated",
    sort_order: str = "desc",
) -> list[dict[str, Any]]:
    """Return source rows with command/KG/drawing enrichment for list responses."""
    if sort_by not in ("created", "updated"):
        raise ValueError("sort_by must be 'created' or 'updated'")
    if sort_order.lower() not in ("asc", "desc"):
        raise ValueError("sort_order must be 'asc' or 'desc'")

    order_clause = f"ORDER BY {sort_by} {sort_order.upper()}"
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if project_id:
        project = await Project.get(project_id)
        if not project:
            raise NotFoundError(f"Project not found: {project_id}")
        query = f"""
            SELECT {_ENRICHED_SOURCE_FIELDS}
            FROM (select value in from reference where out=$project_id)
            {order_clause}
            LIMIT $limit START $offset
            FETCH command, embed_command, kg_command
        """
        params["project_id"] = ensure_record_id(project_id)
    else:
        query = f"""
            SELECT {_ENRICHED_SOURCE_FIELDS}
            FROM source
            {order_clause}
            LIMIT $limit START $offset
            FETCH command, embed_command, kg_command
        """

    result = await repo_query(query, params)
    enriched: list[dict[str, Any]] = []
    for row in result or []:
        enriched.append(await enrich_source_list_row(row))
    return enriched


async def enrich_source_list_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize one SurrealQL list row into a dict ready for SourceListResponse."""
    command = row.get("command")
    command_id = None
    status = None
    processing_info = None

    if command and isinstance(command, dict):
        command_id = str(command.get("id")) if command.get("id") else None
        status = command.get("status")
        result_data = command.get("result")
        execution_metadata = (
            result_data.get("execution_metadata", {})
            if isinstance(result_data, dict)
            else {}
        )
        processing_info = {
            "started_at": execution_metadata.get("started_at"),
            "completed_at": execution_metadata.get("completed_at"),
            "error": command.get("error_message"),
        }
    elif command:
        command_id = str(command)
        status = "unknown"

    pipeline_stage = row.get("pipeline_stage")
    embed_status, has_embed = fetched_command_status(row.get("embed_command"))
    kg_status, has_kg = fetched_command_status(row.get("kg_command"))
    status, stage, _message = resolve_pipeline_status(
        extract_status=status,
        pipeline_stage=pipeline_stage,
        embed_command_status=embed_status,
        kg_command_status=kg_status,
        has_embed_command=has_embed,
        has_kg_command=has_kg,
    )
    source_row_id = str(row["id"])
    await heal_pipeline_stage_if_needed(
        source_row_id,
        current_stage=pipeline_stage,
        resolved_stage=stage,
    )
    processing_info = pipeline_processing_info(processing_info, stage)
    processing_failures = resolve_processing_failures(
        row.get("processing_failures"),
        embed_command=row.get("embed_command"),
        kg_command=row.get("kg_command"),
        kg_run=row.get("latest_kg_run"),
    )
    failure_details_unavailable = stage == "failed" and not processing_failures

    latest_drawing = row.get("latest_drawing_run")
    drawing_status = None
    if isinstance(latest_drawing, dict) and latest_drawing.get("status") is not None:
        drawing_status = str(latest_drawing["status"])

    latest_kg = row.get("latest_kg_run")
    knowledge_graph = (
        isinstance(latest_kg, dict) and str(latest_kg.get("status") or "") == "completed"
    )
    # Prefer durable run completion over command status (mirrors embedded boolean).
    if knowledge_graph:
        kg_status = "completed"

    asset = row.get("asset")
    return {
        "id": row["id"],
        "title": row.get("title"),
        "topics": row.get("topics") or [],
        "asset": asset,
        "embedded": row.get("embedded", False),
        "created": str(row["created"]),
        "updated": str(row["updated"]),
        "command_id": command_id,
        "status": status,
        "processing_info": processing_info,
        "pipeline_stage": pipeline_stage if stage != "failed" else stage,
        "stage": stage,
        "kg_status": kg_status,
        "knowledge_graph": knowledge_graph,
        "drawing_status": drawing_status,
        "processing_failures": processing_failures,
        "failure_details_unavailable": failure_details_unavailable,
    }
