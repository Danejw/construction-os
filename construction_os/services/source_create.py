"""Create a Source and run extract/embed processing (sync or async)."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

from loguru import logger
from surreal_commands import execute_command_sync

import commands.source_commands  # noqa: F401
from commands.source_commands import SourceProcessingInput
from construction_os.config import UPLOADS_FOLDER
from construction_os.database.repository import ensure_record_id
from construction_os.domain.project import Asset, Project, Source
from construction_os.exceptions import InvalidInputError, NotFoundError
from construction_os.jobs import submit_command_job
from construction_os.knowledge.pipeline import PIPELINE_EXTRACTING

SourceType = Literal["link", "upload", "text"]


@dataclass
class SourceCreateResult:
    """Result of create_and_process_source (HTTP layer maps to SourceResponse)."""

    source: Source
    async_queued: bool
    command_id: Optional[str] = None


def build_content_state(
    *,
    source_type: SourceType,
    url: Optional[str] = None,
    content: Optional[str] = None,
    file_path: Optional[str] = None,
    delete_source: bool = False,
) -> dict[str, Any]:
    """Validate inputs and build content_state for process_source."""
    if source_type == "link":
        if not url:
            raise InvalidInputError("URL is required for link type")
        return {"url": url}
    if source_type == "upload":
        if not file_path:
            raise InvalidInputError(
                "File upload or file_path is required for upload type"
            )
        uploads_resolved = Path(UPLOADS_FOLDER).resolve()
        file_resolved = Path(file_path).resolve()
        if not str(file_resolved).startswith(str(uploads_resolved) + os.sep):
            raise InvalidInputError(
                "Invalid file path: must be within the uploads directory"
            )
        return {"file_path": file_path, "delete_source": delete_source}
    if source_type == "text":
        if not content:
            raise InvalidInputError("Content is required for text type")
        return {"content": content}
    raise InvalidInputError("Invalid source type. Must be link, upload, or text")


async def create_and_process_source(
    *,
    source_type: SourceType,
    title: Optional[str] = None,
    projects: Optional[list[str]] = None,
    url: Optional[str] = None,
    content: Optional[str] = None,
    file_path: Optional[str] = None,
    delete_source: bool = False,
    async_processing: bool = False,
) -> SourceCreateResult:
    """Persist a Source, link projects, and process via sync or async command."""
    project_ids = projects or []
    for project_id in project_ids:
        project = await Project.get(project_id)
        if not project:
            raise NotFoundError(f"Project {project_id} not found")

    content_state = build_content_state(
        source_type=source_type,
        url=url,
        content=content,
        file_path=file_path,
        delete_source=delete_source,
    )

    if source_type == "link":
        source_asset: Optional[Asset] = Asset(url=url)
    elif source_type == "upload":
        source_asset = Asset(file_path=file_path)
    else:
        source_asset = None

    source = Source(
        title=title or "Processing...",
        topics=[],
        asset=source_asset,
        pipeline_stage=PIPELINE_EXTRACTING,
    )
    await source.save()

    for project_id in project_ids:
        await source.add_to_project(project_id)

    command_input = SourceProcessingInput(
        source_id=str(source.id),
        content_state=content_state,
        project_ids=project_ids,
        artifacts=[],
        embed=True,
    )

    if async_processing:
        try:
            command_id = submit_command_job(
                "construction_os",
                "process_source",
                command_input.model_dump(),
            )
            source.command = ensure_record_id(command_id)
            await source.save()
            logger.info(f"Submitted async processing command: {command_id}")
            return SourceCreateResult(
                source=source, async_queued=True, command_id=command_id
            )
        except Exception:
            try:
                await source.delete()
            except Exception:
                pass
            raise

    result = await asyncio.to_thread(
        execute_command_sync,
        "construction_os",
        "process_source",
        command_input.model_dump(),
        timeout=300,
    )
    if not result.is_success():
        try:
            await source.delete()
        except Exception:
            pass
        raise RuntimeError(result.error_message or "Processing failed")

    if not source.id:
        raise RuntimeError("Source ID is missing")
    processed = await Source.get(source.id)
    if not processed:
        raise RuntimeError("Processed source not found")
    return SourceCreateResult(source=processed, async_queued=False)
