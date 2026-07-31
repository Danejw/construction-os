import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.project_operator import router
from construction_os.project_operator.models import (
    OperatorAutomationLevel,
    OperatorConfigUpdate,
    OperatorMode,
    OperatorOperation,
)
from construction_os.project_operator.repository import (
    InMemoryProjectOperatorRepository,
)
from construction_os.project_operator.service import ProjectOperatorService


@pytest.mark.asyncio
async def test_operator_is_disabled_by_default() -> None:
    service = ProjectOperatorService(InMemoryProjectOperatorRepository())

    config = await service.get_config("project:alpha")
    result = await service.analyze_project("project:alpha", {"source": "manual"})

    assert config.enabled is False
    assert config.mode == OperatorMode.DISABLED
    assert config.automation_level == OperatorAutomationLevel.DISABLED
    assert result.accepted is False
    assert result.status == "blocked"


@pytest.mark.asyncio
async def test_operator_config_is_isolated_per_project() -> None:
    service = ProjectOperatorService(InMemoryProjectOperatorRepository())
    update = OperatorConfigUpdate(
        enabled=True,
        mode=OperatorMode.MANUAL,
        automation_level=OperatorAutomationLevel.RECOMMEND,
        allowed_source_types=["PDF", "pdf", " Email "],
    )

    alpha = await service.update_config("project:alpha", update)
    beta = await service.get_config("project:beta")

    assert alpha.allowed_source_types == ["pdf", "email"]
    assert alpha.enabled is True
    assert beta.enabled is False


@pytest.mark.asyncio
async def test_recommendation_and_execution_permissions_are_separate() -> None:
    service = ProjectOperatorService(InMemoryProjectOperatorRepository())
    await service.update_config(
        "project:alpha",
        OperatorConfigUpdate(
            enabled=True,
            mode=OperatorMode.MANUAL,
            automation_level=OperatorAutomationLevel.RECOMMEND,
        ),
    )

    proposal = await service.propose_action("project:alpha", {"kind": "draft_email"})
    execution = await service.execute_action(
        "project:alpha", {"kind": "draft_email"}, approved=True
    )

    assert proposal.accepted is True
    assert execution.accepted is False


@pytest.mark.asyncio
async def test_execution_requires_explicit_approval() -> None:
    service = ProjectOperatorService(InMemoryProjectOperatorRepository())
    await service.update_config(
        "project:alpha",
        OperatorConfigUpdate(
            enabled=True,
            mode=OperatorMode.MANUAL,
            automation_level=OperatorAutomationLevel.EXECUTE_APPROVED,
        ),
    )

    unapproved = await service.execute_action(
        "project:alpha", {"kind": "create_task"}, approved=False
    )
    approved = await service.execute_action(
        "project:alpha", {"kind": "create_task"}, approved=True
    )

    assert unapproved.accepted is False
    assert approved.accepted is True


def test_project_operator_api_round_trip() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    project_id = "project:api-foundation"

    default_response = client.get(f"/api/projects/{project_id}/operator/config")
    assert default_response.status_code == 200
    assert default_response.json()["enabled"] is False

    update_response = client.put(
        f"/api/projects/{project_id}/operator/config",
        json={
            "enabled": True,
            "mode": "manual",
            "automation_level": "recommend",
            "allowed_source_types": ["pdf"],
            "approval_policy": {},
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["automation_level"] == "recommend"

    operation_response = client.post(
        f"/api/projects/{project_id}/operator/operations/{OperatorOperation.PROPOSE_ACTION.value}",
        json={"payload": {"kind": "draft_email"}, "approved": False},
    )
    assert operation_response.status_code == 200
    assert operation_response.json()["accepted"] is True
