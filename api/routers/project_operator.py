"""Project-scoped API for configuring and invoking the Project Operator."""

from fastapi import APIRouter

from construction_os.project_operator.models import (
    OperatorConfig,
    OperatorConfigUpdate,
    OperatorOperation,
    OperatorOperationRequest,
    OperatorOperationResult,
)
from construction_os.project_operator.repository import (
    InMemoryProjectOperatorRepository,
)
from construction_os.project_operator.service import ProjectOperatorService

router = APIRouter()
repository = InMemoryProjectOperatorRepository()
service = ProjectOperatorService(repository)


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
