"""API routes for Project Operator evaluation cases and regression suites."""

from fastapi import APIRouter, HTTPException

from api.routers.project_operator import _database_enabled
from construction_os.project_operator.evaluation import (
    CorrectionRegressionCaseRequest,
    EvaluationCase,
    EvaluationCaseCreate,
    EvaluationResult,
    EvaluationSuiteRequest,
    EvaluationSuiteResult,
    InMemoryEvaluationRepository,
    OperatorEvaluationService,
    SurrealEvaluationRepository,
)

router = APIRouter()
evaluation_repository = (
    SurrealEvaluationRepository()
    if _database_enabled
    else InMemoryEvaluationRepository()
)
evaluation_service = OperatorEvaluationService(evaluation_repository)


@router.post(
    "/operator/evaluations/cases",
    response_model=EvaluationCase,
)
async def create_operator_evaluation_case(
    body: EvaluationCaseCreate,
) -> EvaluationCase:
    """Create a fixed, reviewable Project Operator evaluation case."""
    return await evaluation_service.create_case(body)


@router.post(
    "/operator/evaluations/cases/from-correction",
    response_model=EvaluationCase,
)
async def create_regression_case_from_correction(
    body: CorrectionRegressionCaseRequest,
) -> EvaluationCase:
    """Turn a reviewed human correction into a durable regression case."""
    return await evaluation_service.create_case_from_correction(body)


@router.get(
    "/operator/evaluations/cases",
    response_model=list[EvaluationCase],
)
async def list_operator_evaluation_cases() -> list[EvaluationCase]:
    """List the stable evaluation corpus in creation order."""
    return await evaluation_service.list_cases()


@router.post(
    "/operator/evaluations/run",
    response_model=EvaluationSuiteResult,
)
async def run_operator_evaluation_suite(
    body: EvaluationSuiteRequest,
) -> EvaluationSuiteResult:
    """Evaluate one operator and prompt version against every fixed case."""
    try:
        return await evaluation_service.run_suite(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/operator/evaluations/results",
    response_model=list[EvaluationResult],
)
async def list_operator_evaluation_results() -> list[EvaluationResult]:
    """List versioned case results for regression and trend review."""
    return await evaluation_service.list_results()
