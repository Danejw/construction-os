"""API routes for repeatable Project Operator cycles and daily briefs."""

from fastapi import APIRouter, HTTPException

from api.routers.project_operator import (
    _database_enabled,
    action_service,
    extraction_service,
    service,
    signal_service,
)
from construction_os.project_operator.operator_cycle import (
    DailyProjectBrief,
    InMemoryOperatorRunRepository,
    OperatorCycleService,
    OperatorRun,
    OperatorRunRequest,
    SurrealOperatorRunRepository,
)

router = APIRouter()
run_repository = (
    SurrealOperatorRunRepository()
    if _database_enabled
    else InMemoryOperatorRunRepository()
)
cycle_service = OperatorCycleService(
    run_repository,
    service,
    extraction_service,
    signal_service,
    action_service,
)


@router.post(
    "/projects/{project_id}/operator/runs",
    response_model=OperatorRun,
)
async def run_project_operator_cycle(
    project_id: str,
    body: OperatorRunRequest,
) -> OperatorRun:
    """Run extraction, signal detection, recommendations, and approved work."""
    try:
        return await cycle_service.run(project_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/operator/runs",
    response_model=list[OperatorRun],
)
async def list_project_operator_runs(project_id: str) -> list[OperatorRun]:
    """List operator runs in reverse chronological order."""
    return await cycle_service.list_runs(project_id)


@router.get(
    "/projects/{project_id}/operator/daily-brief",
    response_model=DailyProjectBrief,
)
async def get_project_operator_daily_brief(
    project_id: str,
) -> DailyProjectBrief:
    """Build a brief containing only active or unresolved operational items."""
    return await cycle_service.build_daily_brief(project_id)
