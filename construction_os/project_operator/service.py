"""Application service boundary for Project Operator workflows."""

from __future__ import annotations

from construction_os.project_operator.models import (
    OperatorAutomationLevel,
    OperatorConfig,
    OperatorConfigUpdate,
    OperatorMode,
    OperatorOperation,
    OperatorOperationResult,
)
from construction_os.project_operator.permissions import ProjectOperatorPermissions
from construction_os.project_operator.repository import ProjectOperatorRepository


class ProjectOperatorService:
    """Coordinates configuration and guards every operator operation."""

    def __init__(self, repository: ProjectOperatorRepository) -> None:
        self.repository = repository

    async def get_config(self, project_id: str) -> OperatorConfig:
        existing = await self.repository.get_config(project_id)
        if existing:
            return existing
        return OperatorConfig(project_id=project_id)

    async def update_config(
        self, project_id: str, update: OperatorConfigUpdate
    ) -> OperatorConfig:
        config = OperatorConfig(project_id=project_id, **update.model_dump())
        return await self.repository.save_config(config)

    async def ingest_event(
        self, project_id: str, payload: dict[str, object]
    ) -> OperatorOperationResult:
        config = await self.get_config(project_id)
        if not ProjectOperatorPermissions.can_observe(config):
            return self._blocked(project_id, OperatorOperation.INGEST_EVENT)
        return self._accepted(
            project_id,
            OperatorOperation.INGEST_EVENT,
            "Event accepted by the Project Operator boundary.",
            payload,
        )

    async def analyze_project(
        self, project_id: str, payload: dict[str, object]
    ) -> OperatorOperationResult:
        config = await self.get_config(project_id)
        if not ProjectOperatorPermissions.can_observe(config):
            return self._blocked(project_id, OperatorOperation.ANALYZE_PROJECT)
        return self._accepted(
            project_id,
            OperatorOperation.ANALYZE_PROJECT,
            "Project analysis accepted by the Project Operator boundary.",
            payload,
        )

    async def propose_action(
        self, project_id: str, payload: dict[str, object]
    ) -> OperatorOperationResult:
        config = await self.get_config(project_id)
        if not ProjectOperatorPermissions.can_recommend(config):
            return self._blocked(project_id, OperatorOperation.PROPOSE_ACTION)
        return self._accepted(
            project_id,
            OperatorOperation.PROPOSE_ACTION,
            "Action proposal accepted by the Project Operator boundary.",
            payload,
        )

    async def approve_action(
        self, project_id: str, payload: dict[str, object]
    ) -> OperatorOperationResult:
        config = await self.get_config(project_id)
        if not ProjectOperatorPermissions.can_recommend(config):
            return self._blocked(project_id, OperatorOperation.APPROVE_ACTION)
        return self._accepted(
            project_id,
            OperatorOperation.APPROVE_ACTION,
            "Action approval accepted by the Project Operator boundary.",
            payload,
        )

    async def execute_action(
        self,
        project_id: str,
        payload: dict[str, object],
        *,
        approved: bool,
    ) -> OperatorOperationResult:
        config = await self.get_config(project_id)
        if not ProjectOperatorPermissions.can_execute_approved(
            config, approved=approved
        ):
            return self._blocked(project_id, OperatorOperation.EXECUTE_ACTION)
        return self._accepted(
            project_id,
            OperatorOperation.EXECUTE_ACTION,
            "Approved action accepted by the Project Operator boundary.",
            payload,
        )

    async def dispatch(
        self,
        project_id: str,
        operation: OperatorOperation,
        payload: dict[str, object],
        *,
        approved: bool = False,
    ) -> OperatorOperationResult:
        handlers = {
            OperatorOperation.INGEST_EVENT: self.ingest_event,
            OperatorOperation.ANALYZE_PROJECT: self.analyze_project,
            OperatorOperation.PROPOSE_ACTION: self.propose_action,
            OperatorOperation.APPROVE_ACTION: self.approve_action,
        }
        if operation == OperatorOperation.EXECUTE_ACTION:
            return await self.execute_action(
                project_id, payload, approved=approved
            )
        return await handlers[operation](project_id, payload)

    @staticmethod
    def _blocked(
        project_id: str, operation: OperatorOperation
    ) -> OperatorOperationResult:
        return OperatorOperationResult(
            project_id=project_id,
            operation=operation,
            accepted=False,
            status="blocked",
            detail="Project Operator permissions block this operation.",
        )

    @staticmethod
    def _accepted(
        project_id: str,
        operation: OperatorOperation,
        detail: str,
        payload: dict[str, object],
    ) -> OperatorOperationResult:
        return OperatorOperationResult(
            project_id=project_id,
            operation=operation,
            accepted=True,
            status="accepted",
            detail=detail,
            payload=payload,
        )


def default_active_config(project_id: str) -> OperatorConfig:
    """Convenience configuration for manual recommendation-only pilots."""
    return OperatorConfig(
        project_id=project_id,
        enabled=True,
        mode=OperatorMode.MANUAL,
        automation_level=OperatorAutomationLevel.RECOMMEND,
    )
