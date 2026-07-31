"""Permission rules for bounded Project Operator behavior."""

from construction_os.project_operator.models import (
    OperatorAutomationLevel,
    OperatorConfig,
)


class ProjectOperatorPermissions:
    """Central policy checks used before any operator workflow is accepted."""

    @staticmethod
    def can_observe(config: OperatorConfig) -> bool:
        return config.enabled and config.automation_level in {
            OperatorAutomationLevel.OBSERVE_ONLY,
            OperatorAutomationLevel.RECOMMEND,
            OperatorAutomationLevel.EXECUTE_APPROVED,
        }

    @staticmethod
    def can_recommend(config: OperatorConfig) -> bool:
        return config.enabled and config.automation_level in {
            OperatorAutomationLevel.RECOMMEND,
            OperatorAutomationLevel.EXECUTE_APPROVED,
        }

    @staticmethod
    def can_execute_approved(config: OperatorConfig, *, approved: bool) -> bool:
        return (
            approved
            and config.enabled
            and config.automation_level
            == OperatorAutomationLevel.EXECUTE_APPROVED
        )
