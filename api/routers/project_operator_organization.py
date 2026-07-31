"""API routes for organization-level Project Operator capabilities."""

from fastapi import APIRouter, HTTPException

from api.routers.project_operator import (
    _database_enabled,
    signal_service,
    state_service,
)
from construction_os.project_operator.organization_operator import (
    InMemoryOrganizationOperatorRepository,
    Organization,
    OrganizationAction,
    OrganizationActionCreate,
    OrganizationActionDecision,
    OrganizationCreate,
    OrganizationOperatorService,
    OrganizationOverview,
    OrganizationProjectAccess,
    OrganizationProjectAccessCreate,
    ResourceAssignment,
    ResourceAssignmentCreate,
    SharedParty,
    SharedPartyCreate,
    SurrealOrganizationOperatorRepository,
)

router = APIRouter()
organization_repository = (
    SurrealOrganizationOperatorRepository()
    if _database_enabled
    else InMemoryOrganizationOperatorRepository()
)
organization_service = OrganizationOperatorService(
    organization_repository,
    state_service,
    signal_service,
)


@router.post(
    "/operator/organizations",
    response_model=Organization,
)
async def create_operator_organization(body: OrganizationCreate) -> Organization:
    """Create an organization with its own approval policy."""
    return await organization_service.create_organization(body)


@router.post(
    "/operator/organizations/{organization_id}/projects",
    response_model=OrganizationProjectAccess,
)
async def add_organization_project(
    organization_id: str,
    body: OrganizationProjectAccessCreate,
) -> OrganizationProjectAccess:
    """Grant organization-scoped view or operate access to one project."""
    try:
        return await organization_service.add_project_access(organization_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/operator/organizations/{organization_id}/parties",
    response_model=SharedParty,
)
async def register_organization_party(
    organization_id: str,
    body: SharedPartyCreate,
) -> SharedParty:
    """Register or reuse a normalized employee, vendor, client, or subcontractor."""
    try:
        return await organization_service.register_party(organization_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/operator/organizations/{organization_id}/resource-assignments",
    response_model=ResourceAssignment,
)
async def assign_organization_resource(
    organization_id: str,
    body: ResourceAssignmentCreate,
) -> ResourceAssignment:
    """Assign a shared resource to an authorized project window."""
    try:
        return await organization_service.assign_resource(organization_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/operator/organizations/{organization_id}/overview",
    response_model=OrganizationOverview,
)
async def get_organization_operator_overview(
    organization_id: str,
) -> OrganizationOverview:
    """Build a read-only company view from authorized project state."""
    try:
        return await organization_service.build_overview(organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/operator/organizations/{organization_id}/actions",
    response_model=OrganizationAction,
)
async def propose_organization_action(
    organization_id: str,
    body: OrganizationActionCreate,
) -> OrganizationAction:
    """Propose a company-level action across operable projects."""
    try:
        return await organization_service.propose_action(organization_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post(
    "/operator/organizations/{organization_id}/actions/{action_id}/decision",
    response_model=OrganizationAction,
)
async def decide_organization_action(
    organization_id: str,
    action_id: str,
    body: OrganizationActionDecision,
) -> OrganizationAction:
    """Apply the organization's separate action-approval policy."""
    try:
        return await organization_service.decide_action(
            organization_id,
            action_id,
            body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get(
    "/operator/organizations/{organization_id}/actions",
    response_model=list[OrganizationAction],
)
async def list_organization_actions(
    organization_id: str,
) -> list[OrganizationAction]:
    """List company-level proposed, approved, and rejected actions."""
    try:
        return await organization_service.list_actions(organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
