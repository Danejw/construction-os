from typing import Optional

from pydantic import field_validator
from surreal_commands import CommandInput, CommandOutput, command

from construction_os.exceptions import InvalidInputError
from construction_os.services.artifact_review import run_artifact_review


class ReviewArtifactInput(CommandInput):
    note_id: str
    project_id: str
    run_id: str
    model_id: Optional[str] = None

    @field_validator("note_id", "project_id", "run_id")
    @classmethod
    def non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("id fields cannot be empty")
        return normalized


class ReviewArtifactOutput(CommandOutput):
    success: bool
    run_id: str
    status: str


@command(
    "review_artifact",
    app="construction_os",
    retry={
        "max_attempts": 3,
        "wait_strategy": "exponential_jitter",
        "wait_min": 2,
        "wait_max": 60,
        "stop_on": [ValueError, InvalidInputError],
        "retry_log_level": "debug",
    },
)
async def review_artifact_command(
    input_data: ReviewArtifactInput,
) -> ReviewArtifactOutput:
    run = await run_artifact_review(
        note_id=input_data.note_id,
        project_id=input_data.project_id,
        run_id=input_data.run_id,
        model_id=input_data.model_id,
    )
    return ReviewArtifactOutput(
        success=run.status != "failed",
        run_id=str(run.id),
        status=run.status,
    )
