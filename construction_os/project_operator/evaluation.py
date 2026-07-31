"""Versioned Project Operator evaluations, metrics, and regression cases."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from construction_os.database.repository import ensure_record_id, repo_query
from construction_os.project_operator.action_runtime import OperatorActionType
from construction_os.project_operator.signal_detection import ProjectSignalType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationCaseCreate(BaseModel):
    name: str
    description: str
    input_sources: list[dict[str, object]] = Field(default_factory=list)
    existing_project_state: list[dict[str, object]] = Field(default_factory=list)
    expected_observations: list[str] = Field(default_factory=list)
    expected_signals: list[ProjectSignalType] = Field(default_factory=list)
    expected_actions: list[OperatorActionType] = Field(default_factory=list)
    forbidden_actions: list[OperatorActionType] = Field(default_factory=list)
    required_evidence_refs: list[str] = Field(default_factory=list)
    reviewer_notes: str | None = None
    correction_event_id: str | None = None
    is_regression: bool = True

    @field_validator("name", "description")
    @classmethod
    def required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("evaluation name and description cannot be empty")
        return normalized


class EvaluationCase(EvaluationCaseCreate):
    id: str
    created_at: datetime = Field(default_factory=utc_now)


class OperationalEvaluationMetrics(BaseModel):
    proposed_action_count: int = Field(default=0, ge=0)
    approved_action_count: int = Field(default=0, ge=0)
    execution_success_count: int = Field(default=0, ge=0)
    execution_failure_count: int = Field(default=0, ge=0)
    human_correction_count: int = Field(default=0, ge=0)
    time_saved_minutes: float = Field(default=0, ge=0)


class EvaluationSubmission(BaseModel):
    observed_categories: list[str] = Field(default_factory=list)
    signal_types: list[ProjectSignalType] = Field(default_factory=list)
    action_types: list[OperatorActionType] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    permission_violations: list[str] = Field(default_factory=list)
    operational_metrics: OperationalEvaluationMetrics = Field(
        default_factory=OperationalEvaluationMetrics
    )


class ComponentScore(BaseModel):
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    false_positives: list[str]
    missed: list[str]


class EvaluationResult(BaseModel):
    id: str
    case_id: str
    operator_version: str
    prompt_version: str
    observation_score: ComponentScore
    signal_score: ComponentScore
    action_score: ComponentScore
    evidence_accuracy: float = Field(ge=0, le=1)
    missing_evidence_refs: list[str]
    forbidden_actions_detected: list[OperatorActionType]
    permission_violations: list[str]
    permission_compliant: bool
    execution_success_rate: float = Field(ge=0, le=1)
    action_approval_rate: float = Field(ge=0, le=1)
    human_correction_rate: float = Field(ge=0, le=1)
    time_saved_minutes: float = Field(ge=0)
    passed: bool
    created_at: datetime = Field(default_factory=utc_now)


class EvaluationSuiteRequest(BaseModel):
    operator_version: str
    prompt_version: str
    submissions: dict[str, EvaluationSubmission]

    @field_validator("operator_version", "prompt_version")
    @classmethod
    def required_version(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("operator and prompt versions cannot be empty")
        return normalized


class EvaluationSuiteResult(BaseModel):
    id: str
    operator_version: str
    prompt_version: str
    case_results: list[EvaluationResult]
    observation_precision: float = Field(ge=0, le=1)
    observation_recall: float = Field(ge=0, le=1)
    signal_precision: float = Field(ge=0, le=1)
    signal_recall: float = Field(ge=0, le=1)
    action_precision: float = Field(ge=0, le=1)
    action_recall: float = Field(ge=0, le=1)
    evidence_accuracy: float = Field(ge=0, le=1)
    permission_compliant: bool
    pass_rate: float = Field(ge=0, le=1)
    created_at: datetime = Field(default_factory=utc_now)


class CorrectionRegressionCaseRequest(BaseModel):
    name: str
    description: str
    correction_event_id: str
    input_sources: list[dict[str, object]]
    existing_project_state: list[dict[str, object]] = Field(default_factory=list)
    expected_observations: list[str] = Field(default_factory=list)
    expected_signals: list[ProjectSignalType] = Field(default_factory=list)
    expected_actions: list[OperatorActionType] = Field(default_factory=list)
    forbidden_actions: list[OperatorActionType] = Field(default_factory=list)
    required_evidence_refs: list[str] = Field(default_factory=list)
    reviewer_notes: str | None = None


class EvaluationRepository(Protocol):
    async def save_case(self, case: EvaluationCase) -> EvaluationCase: ...

    async def get_case(self, case_id: str) -> EvaluationCase | None: ...

    async def list_cases(self) -> list[EvaluationCase]: ...

    async def save_result(self, result: EvaluationResult) -> EvaluationResult: ...

    async def list_results(self) -> list[EvaluationResult]: ...


class InMemoryEvaluationRepository:
    def __init__(self) -> None:
        self._cases: dict[str, EvaluationCase] = {}
        self._results: dict[str, EvaluationResult] = {}
        self._lock = asyncio.Lock()

    async def save_case(self, case: EvaluationCase) -> EvaluationCase:
        async with self._lock:
            self._cases[case.id] = case.model_copy(deep=True)
            return case.model_copy(deep=True)

    async def get_case(self, case_id: str) -> EvaluationCase | None:
        async with self._lock:
            case = self._cases.get(case_id)
            return case.model_copy(deep=True) if case else None

    async def list_cases(self) -> list[EvaluationCase]:
        async with self._lock:
            return sorted(
                [case.model_copy(deep=True) for case in self._cases.values()],
                key=lambda item: item.created_at,
            )

    async def save_result(self, result: EvaluationResult) -> EvaluationResult:
        async with self._lock:
            self._results[result.id] = result.model_copy(deep=True)
            return result.model_copy(deep=True)

    async def list_results(self) -> list[EvaluationResult]:
        async with self._lock:
            return sorted(
                [result.model_copy(deep=True) for result in self._results.values()],
                key=lambda item: item.created_at,
                reverse=True,
            )


class SurrealEvaluationRepository:
    async def _ensure_tables(self) -> None:
        await repo_query(
            "DEFINE TABLE IF NOT EXISTS operator_evaluation_case SCHEMALESS; "
            "DEFINE TABLE IF NOT EXISTS operator_evaluation_result SCHEMALESS;"
        )

    async def save_case(self, case: EvaluationCase) -> EvaluationCase:
        await self._ensure_tables()
        result = await repo_query(
            "UPSERT $id CONTENT $data RETURN AFTER;",
            {
                "id": ensure_record_id(case.id),
                "data": case.model_dump(mode="json", exclude={"id"}),
            },
        )
        return EvaluationCase(id=case.id, **result[0])

    async def get_case(self, case_id: str) -> EvaluationCase | None:
        await self._ensure_tables()
        result = await repo_query(
            "SELECT * FROM $id;",
            {"id": ensure_record_id(case_id)},
        )
        return EvaluationCase(id=case_id, **result[0]) if result else None

    async def list_cases(self) -> list[EvaluationCase]:
        await self._ensure_tables()
        result = await repo_query(
            "SELECT * FROM operator_evaluation_case ORDER BY created_at ASC;"
        )
        return [EvaluationCase(**item) for item in result]

    async def save_result(self, result: EvaluationResult) -> EvaluationResult:
        await self._ensure_tables()
        stored = await repo_query(
            "UPSERT $id CONTENT $data RETURN AFTER;",
            {
                "id": ensure_record_id(result.id),
                "data": result.model_dump(mode="json", exclude={"id"}),
            },
        )
        return EvaluationResult(id=result.id, **stored[0])

    async def list_results(self) -> list[EvaluationResult]:
        await self._ensure_tables()
        result = await repo_query(
            "SELECT * FROM operator_evaluation_result ORDER BY created_at DESC;"
        )
        return [EvaluationResult(**item) for item in result]


class OperatorEvaluationService:
    """Evaluates operator versions against stable, reviewable expectations."""

    def __init__(self, repository: EvaluationRepository) -> None:
        self.repository = repository

    async def create_case(self, body: EvaluationCaseCreate) -> EvaluationCase:
        case = EvaluationCase(
            id=f"operator_evaluation_case:{uuid4().hex}",
            **body.model_dump(),
        )
        return await self.repository.save_case(case)

    async def create_case_from_correction(
        self,
        body: CorrectionRegressionCaseRequest,
    ) -> EvaluationCase:
        return await self.create_case(
            EvaluationCaseCreate(
                name=body.name,
                description=body.description,
                input_sources=body.input_sources,
                existing_project_state=body.existing_project_state,
                expected_observations=body.expected_observations,
                expected_signals=body.expected_signals,
                expected_actions=body.expected_actions,
                forbidden_actions=body.forbidden_actions,
                required_evidence_refs=body.required_evidence_refs,
                reviewer_notes=body.reviewer_notes,
                correction_event_id=body.correction_event_id,
                is_regression=True,
            )
        )

    async def list_cases(self) -> list[EvaluationCase]:
        return await self.repository.list_cases()

    async def evaluate_case(
        self,
        case: EvaluationCase,
        submission: EvaluationSubmission,
        *,
        operator_version: str,
        prompt_version: str,
    ) -> EvaluationResult:
        observation_score = self._score_sets(
            case.expected_observations,
            submission.observed_categories,
        )
        signal_score = self._score_sets(
            [item.value for item in case.expected_signals],
            [item.value for item in submission.signal_types],
        )
        action_score = self._score_sets(
            [item.value for item in case.expected_actions],
            [item.value for item in submission.action_types],
        )
        evidence_expected = set(case.required_evidence_refs)
        evidence_actual = set(submission.evidence_refs)
        missing_evidence = sorted(evidence_expected - evidence_actual)
        evidence_accuracy = (
            len(evidence_expected & evidence_actual) / len(evidence_expected)
            if evidence_expected
            else 1.0
        )
        forbidden = sorted(
            set(case.forbidden_actions) & set(submission.action_types),
            key=lambda item: item.value,
        )
        operational = submission.operational_metrics
        execution_total = (
            operational.execution_success_count
            + operational.execution_failure_count
        )
        execution_success_rate = (
            operational.execution_success_count / execution_total
            if execution_total
            else 1.0
        )
        action_approval_rate = (
            operational.approved_action_count
            / operational.proposed_action_count
            if operational.proposed_action_count
            else 0.0
        )
        correction_denominator = max(
            len(submission.observed_categories)
            + len(submission.signal_types)
            + len(submission.action_types),
            1,
        )
        human_correction_rate = (
            operational.human_correction_count / correction_denominator
        )
        permission_compliant = not submission.permission_violations and not forbidden
        passed = all(
            [
                observation_score.recall == 1.0,
                signal_score.recall == 1.0,
                action_score.recall == 1.0,
                not observation_score.false_positives,
                not signal_score.false_positives,
                not action_score.false_positives,
                evidence_accuracy == 1.0,
                permission_compliant,
                execution_success_rate == 1.0,
            ]
        )
        result = EvaluationResult(
            id=f"operator_evaluation_result:{uuid4().hex}",
            case_id=case.id,
            operator_version=operator_version,
            prompt_version=prompt_version,
            observation_score=observation_score,
            signal_score=signal_score,
            action_score=action_score,
            evidence_accuracy=evidence_accuracy,
            missing_evidence_refs=missing_evidence,
            forbidden_actions_detected=forbidden,
            permission_violations=submission.permission_violations,
            permission_compliant=permission_compliant,
            execution_success_rate=execution_success_rate,
            action_approval_rate=action_approval_rate,
            human_correction_rate=human_correction_rate,
            time_saved_minutes=operational.time_saved_minutes,
            passed=passed,
        )
        return await self.repository.save_result(result)

    async def run_suite(
        self,
        request: EvaluationSuiteRequest,
    ) -> EvaluationSuiteResult:
        cases = await self.repository.list_cases()
        missing = [case.id for case in cases if case.id not in request.submissions]
        if missing:
            raise ValueError(f"missing submissions for evaluation cases: {missing}")
        results = [
            await self.evaluate_case(
                case,
                request.submissions[case.id],
                operator_version=request.operator_version,
                prompt_version=request.prompt_version,
            )
            for case in cases
        ]
        return EvaluationSuiteResult(
            id=f"operator_evaluation_suite:{uuid4().hex}",
            operator_version=request.operator_version,
            prompt_version=request.prompt_version,
            case_results=results,
            observation_precision=self._average(
                [item.observation_score.precision for item in results]
            ),
            observation_recall=self._average(
                [item.observation_score.recall for item in results]
            ),
            signal_precision=self._average(
                [item.signal_score.precision for item in results]
            ),
            signal_recall=self._average(
                [item.signal_score.recall for item in results]
            ),
            action_precision=self._average(
                [item.action_score.precision for item in results]
            ),
            action_recall=self._average(
                [item.action_score.recall for item in results]
            ),
            evidence_accuracy=self._average(
                [item.evidence_accuracy for item in results]
            ),
            permission_compliant=all(
                item.permission_compliant for item in results
            ),
            pass_rate=self._average(
                [1.0 if item.passed else 0.0 for item in results]
            ),
        )

    async def list_results(self) -> list[EvaluationResult]:
        return await self.repository.list_results()

    @staticmethod
    def _score_sets(expected: list[str], actual: list[str]) -> ComponentScore:
        expected_set = set(expected)
        actual_set = set(actual)
        true_positive_count = len(expected_set & actual_set)
        precision = (
            true_positive_count / len(actual_set) if actual_set else 1.0
        )
        recall = (
            true_positive_count / len(expected_set) if expected_set else 1.0
        )
        return ComponentScore(
            precision=precision,
            recall=recall,
            false_positives=sorted(actual_set - expected_set),
            missed=sorted(expected_set - actual_set),
        )

    @staticmethod
    def _average(values: list[float]) -> float:
        return sum(values) / len(values) if values else 1.0
