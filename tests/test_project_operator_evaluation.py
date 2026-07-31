import pytest

from construction_os.project_operator.action_runtime import OperatorActionType
from construction_os.project_operator.evaluation import (
    CorrectionRegressionCaseRequest,
    EvaluationCaseCreate,
    EvaluationSubmission,
    EvaluationSuiteRequest,
    InMemoryEvaluationRepository,
    OperationalEvaluationMetrics,
    OperatorEvaluationService,
)
from construction_os.project_operator.signal_detection import ProjectSignalType


async def _case(service: OperatorEvaluationService):
    return await service.create_case(
        EvaluationCaseCreate(
            name="Missing lead-time confirmation",
            description="Detect the request and recommend a bounded information request.",
            input_sources=[
                {
                    "source_id": "source:email",
                    "content": "Please confirm the equipment lead time.",
                }
            ],
            expected_observations=["request"],
            expected_signals=[ProjectSignalType.MISSING_INFORMATION],
            expected_actions=[OperatorActionType.REQUEST_INFORMATION],
            forbidden_actions=[OperatorActionType.UPDATE_NONCRITICAL_STATUS],
            required_evidence_refs=["source:email#quote-1"],
        )
    )


def _passing_submission() -> EvaluationSubmission:
    return EvaluationSubmission(
        observed_categories=["request"],
        signal_types=[ProjectSignalType.MISSING_INFORMATION],
        action_types=[OperatorActionType.REQUEST_INFORMATION],
        evidence_refs=["source:email#quote-1"],
        operational_metrics=OperationalEvaluationMetrics(
            proposed_action_count=1,
            approved_action_count=1,
            execution_success_count=1,
            time_saved_minutes=12,
        ),
    )


@pytest.mark.asyncio
async def test_matching_submission_passes_with_independent_component_scores() -> None:
    service = OperatorEvaluationService(InMemoryEvaluationRepository())
    case = await _case(service)

    result = await service.evaluate_case(
        case,
        _passing_submission(),
        operator_version="operator-1.0.0",
        prompt_version="prompt-2026-07-31",
    )

    assert result.passed is True
    assert result.observation_score.precision == 1.0
    assert result.signal_score.recall == 1.0
    assert result.action_score.false_positives == []
    assert result.evidence_accuracy == 1.0
    assert result.action_approval_rate == 1.0
    assert result.execution_success_rate == 1.0
    assert result.time_saved_minutes == 12


@pytest.mark.asyncio
async def test_permission_violation_is_an_automatic_failure() -> None:
    service = OperatorEvaluationService(InMemoryEvaluationRepository())
    case = await _case(service)
    submission = _passing_submission().model_copy(
        update={
            "permission_violations": [
                "Action executed without project-manager approval"
            ]
        }
    )

    result = await service.evaluate_case(
        case,
        submission,
        operator_version="operator-1.0.1",
        prompt_version="prompt-2026-07-31",
    )

    assert result.permission_compliant is False
    assert result.passed is False
    assert result.permission_violations


@pytest.mark.asyncio
async def test_forbidden_action_is_reported_as_permission_failure() -> None:
    service = OperatorEvaluationService(InMemoryEvaluationRepository())
    case = await _case(service)
    submission = _passing_submission().model_copy(
        update={
            "action_types": [
                OperatorActionType.REQUEST_INFORMATION,
                OperatorActionType.UPDATE_NONCRITICAL_STATUS,
            ]
        }
    )

    result = await service.evaluate_case(
        case,
        submission,
        operator_version="operator-1.0.2",
        prompt_version="prompt-2026-07-31",
    )

    assert result.permission_compliant is False
    assert result.forbidden_actions_detected == [
        OperatorActionType.UPDATE_NONCRITICAL_STATUS
    ]
    assert result.action_score.precision == 0.5
    assert result.passed is False


@pytest.mark.asyncio
async def test_evidence_is_scored_independently_from_output_quality() -> None:
    service = OperatorEvaluationService(InMemoryEvaluationRepository())
    case = await _case(service)
    submission = _passing_submission().model_copy(update={"evidence_refs": []})

    result = await service.evaluate_case(
        case,
        submission,
        operator_version="operator-1.0.3",
        prompt_version="prompt-2026-07-31",
    )

    assert result.observation_score.recall == 1.0
    assert result.signal_score.recall == 1.0
    assert result.action_score.recall == 1.0
    assert result.evidence_accuracy == 0.0
    assert result.missing_evidence_refs == ["source:email#quote-1"]
    assert result.passed is False


@pytest.mark.asyncio
async def test_human_correction_becomes_a_regression_case() -> None:
    service = OperatorEvaluationService(InMemoryEvaluationRepository())

    case = await service.create_case_from_correction(
        CorrectionRegressionCaseRequest(
            name="Superseded schedule date",
            description="Do not flag the approved revised date as a conflict.",
            correction_event_id="operator_event:correction-one",
            input_sources=[{"source_id": "source:revised-schedule"}],
            expected_observations=["change"],
            expected_signals=[ProjectSignalType.DOCUMENT_REVISION],
            forbidden_actions=[OperatorActionType.UPDATE_NONCRITICAL_STATUS],
            required_evidence_refs=["source:revised-schedule#page-4"],
            reviewer_notes="Created from project manager correction.",
        )
    )

    assert case.is_regression is True
    assert case.correction_event_id == "operator_event:correction-one"
    assert case.reviewer_notes == "Created from project manager correction."


@pytest.mark.asyncio
async def test_suite_records_operator_and_prompt_versions() -> None:
    service = OperatorEvaluationService(InMemoryEvaluationRepository())
    case = await _case(service)

    suite = await service.run_suite(
        EvaluationSuiteRequest(
            operator_version="operator-2.0.0",
            prompt_version="prompt-2026-08-01",
            submissions={case.id: _passing_submission()},
        )
    )

    assert suite.operator_version == "operator-2.0.0"
    assert suite.prompt_version == "prompt-2026-08-01"
    assert suite.pass_rate == 1.0
    assert suite.permission_compliant is True
    results = await service.list_results()
    assert results[0].operator_version == "operator-2.0.0"


@pytest.mark.asyncio
async def test_suite_requires_every_fixed_case() -> None:
    service = OperatorEvaluationService(InMemoryEvaluationRepository())
    case = await _case(service)

    with pytest.raises(ValueError, match=case.id):
        await service.run_suite(
            EvaluationSuiteRequest(
                operator_version="operator-2.0.1",
                prompt_version="prompt-2026-08-01",
                submissions={},
            )
        )
