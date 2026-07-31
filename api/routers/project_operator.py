"""Project-scoped API for configuring and operating the Project Operator."""

from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from construction_os.project_operator.approval_inbox import (
    ApprovalInboxService,
    OperatorApprovalInbox,
    SignalCorrectionRequest,
)
from construction_os.project_operator.event_ledger import (
    InMemoryProjectEventRepository,
    ProjectEvent,
    ProjectEventCreate,
    ProjectEventLedgerService,
    RecordTransitionRequest,
    StateReconciliationService,
    SurrealProjectEventRepository,
)
from construction_os.project_operator.models import (
    OperatorConfig,
    OperatorConfigUpdate,
    OperatorOperation,
    OperatorOperationRequest,
    OperatorOperationResult,
)
from construction_os.project_operator.observation_extraction import (
    ObservationExtractionService,
    SourceObservationRequest,
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
from construction_os.project_operator.signal_detection import (
    InMemoryProjectSignalRepository,
    ProjectSignal,
    ProjectSignalDetectionService,
    ProjectSignalStatus,
    SurrealProjectSignalRepository,
)

router = APIRouter()
repository = InMemoryProjectOperatorRepository()
service = ProjectOperatorService(repository)
_database_enabled = bool(os.getenv("SURREAL_URL") or os.getenv("SURREAL_ADDRESS"))
state_repository = (
    SurrealOperationalStateRepository()
    if _database_enabled
    else InMemoryOperationalStateRepository()
)
event_repository = (
    SurrealProjectEventRepository()
    if _database_enabled
    else InMemoryProjectEventRepository()
)
signal_repository = (
    SurrealProjectSignalRepository()
    if _database_enabled
    else InMemoryProjectSignalRepository()
)
state_service = OperationalStateService(state_repository)
event_service = ProjectEventLedgerService(event_repository)
reconciliation_service = StateReconciliationService(state_repository, event_service)
extraction_service = ObservationExtractionService(state_service, event_service)
signal_service = ProjectSignalDetectionService(state_service, signal_repository)
inbox_service = ApprovalInboxService(signal_service, event_service)


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


@router.post(
    "/projects/{project_id}/operator/events",
    response_model=ProjectEvent,
)
async def append_project_event(
    project_id: str, body: ProjectEventCreate
) -> ProjectEvent:
    """Append an immutable event to the project's operational ledger."""
    try:
        return await event_service.append(project_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/operator/events",
    response_model=list[ProjectEvent],
)
async def list_project_events(
    project_id: str,
    entity_id: str | None = Query(default=None),
) -> list[ProjectEvent]:
    """List project events in deterministic sequence order."""
    try:
        return await event_service.list_events(project_id, entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/operator/state/{record_id}/transition",
    response_model=OperationalRecord,
)
async def transition_operational_record(
    project_id: str,
    record_id: str,
    body: RecordTransitionRequest,
) -> OperationalRecord:
    """Change current state while preserving the full prior state in the ledger."""
    try:
        record, _event = await reconciliation_service.transition(
            project_id, record_id, body
        )
        return record
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/operator/sources/{source_id}/extract-observations",
    response_model=list[OperationalRecord],
)
async def extract_source_observations(
    project_id: str,
    source_id: str,
    body: SourceObservationRequest,
) -> list[OperationalRecord]:
    """Extract conservative, evidence-backed observations from source text."""
    try:
        return await extraction_service.extract_and_store(project_id, source_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/operator/signals/detect",
    response_model=list[ProjectSignal],
)
async def detect_project_signals(
    project_id: str,
    now: datetime | None = Query(default=None),
) -> list[ProjectSignal]:
    """Compare observations and accepted state to produce actionable signals."""
    try:
        return await signal_service.detect(project_id, now=now)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/operator/signals",
    response_model=list[ProjectSignal],
)
async def list_project_signals(
    project_id: str,
    status: ProjectSignalStatus | None = Query(default=None),
) -> list[ProjectSignal]:
    """List project signals, optionally filtered by review status."""
    return await signal_service.list_signals(project_id, status)


@router.put(
    "/projects/{project_id}/operator/signals/{signal_id}/status",
    response_model=ProjectSignal,
)
async def update_project_signal_status(
    project_id: str,
    signal_id: str,
    status: ProjectSignalStatus = Query(...),
) -> ProjectSignal:
    """Record review, dismissal, resolution, or conversion of a signal."""
    try:
        return await signal_service.update_status(project_id, signal_id, status)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/operator/inbox",
    response_model=OperatorApprovalInbox,
)
async def get_operator_approval_inbox(project_id: str) -> OperatorApprovalInbox:
    """Return the stable human-review projection for a project's operator."""
    return await inbox_service.build(project_id)


@router.post(
    "/projects/{project_id}/operator/signals/{signal_id}/correction",
    response_model=ProjectSignal,
)
async def correct_project_signal(
    project_id: str,
    signal_id: str,
    body: SignalCorrectionRequest,
) -> ProjectSignal:
    """Capture a human correction and resolve the incorrect signal."""
    try:
        return await inbox_service.correct_signal(project_id, signal_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
