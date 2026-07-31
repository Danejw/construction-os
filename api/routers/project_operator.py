"""Project-scoped API for configuring and operating the Project Operator."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query

from construction_os.project_operator.models import (
    OperatorConfig,
    OperatorConfigUpdate,
    OperatorOperation,
    OperatorOperationRequest,
    OperatorOperationResult,
)
from construction_os.project_operator.operational_state import (
    EvidenceCreate,
    EvidenceRecord,
    InMemoryOperationalStateRepository,
    OperationalRecord,
    OperationalRecordCreate,
    OperationalRecordType,
    OperationalStateService,
    OperationalStatus,
    SurrealOperationalStateRepository,
)
from construction_os.project_operator.repository import (
    InMemoryProjectOperatorRepository,
)
from construction_os.project_operator.service import ProjectOperatorService

router = APIRouter()
repository = InMemoryProjectOperatorRepository()
service = ProjectOperatorService(repository)
state_repository = (
    SurrealOperationalStateRepository()
    if os.getenv("SURREAL_URL") or os.getenv("SURREAL_ADDRESS")
    else InMemoryOperationalStateRepository()
)
state_service = OperationalStateService(state_repository)


@router.get(
    "/projects/{project_id}/operator/config",
    response_model=OperatorConfig,
)
async def get_project_operator_config(project_id: str) -> OperatorConfig:
    """Return a project's operator configuration, disabled by default."""
    return await service.get_config(project_id)


@router.put(
    "/projects/{project_id}/operator/config",
    response_model=OperatorConfig,
)
async def update_project_operator_config(
    project_id: str, body: OperatorConfigUpdate
) -> OperatorConfig:
    """Create or replace a project's operator configuration."""
    return await service.update_config(project_id, body)


@router.post(
    "/projects/{project_id}/operator/operations/{operation}",
    response_model=OperatorOperationResult,
)
async def run_project_operator_operation(
    project_id: str,
    operation: OperatorOperation,
    body: OperatorOperationRequest,
) -> OperatorOperationResult:
    """Invoke a bounded operator service operation after permission checks."""
    return await service.dispatch(
        project_id,
        operation,
        body.payload,
        approved=body.approved,
    )


@router.post(
    "/projects/{project_id}/operator/evidence",
    response_model=EvidenceRecord,
)
async def create_operator_evidence(
    project_id: str, body: EvidenceCreate
) -> EvidenceRecord:
    """Create a precise evidence reference scoped to one project."""
    try:
        return await state_service.create_evidence(project_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/operator/state",
    response_model=OperationalRecord,
)
async def create_operational_record(
    project_id: str, body: OperationalRecordCreate
) -> OperationalRecord:
    """Create a typed operational record only when its evidence is available."""
    try:
        return await state_service.create_record(project_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/operator/state",
    response_model=list[OperationalRecord],
)
async def list_operational_records(
    project_id: str,
    record_type: OperationalRecordType | None = Query(default=None),
    status: OperationalStatus | None = Query(default=None),
) -> list[OperationalRecord]:
    """List a project's operational state with optional type and status filters."""
    try:
        return await state_service.list_records(project_id, record_type, status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
