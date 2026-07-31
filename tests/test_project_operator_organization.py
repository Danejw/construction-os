from datetime import datetime, timezone

import pytest

from construction_os.project_operator.operational_state import (
    EvidenceCreate,
    InMemoryOperationalStateRepository,
    OperationalRecordCreate,
    OperationalRecordType,
    OperationalStateService,
    OperationalStatus,
)
from construction_os.project_operator.organization_operator import (
    InMemoryOrganizationOperatorRepository,
    OrganizationActionCreate,
    OrganizationActionDecision,
    OrganizationActionStatus,
    OrganizationActionType,
    OrganizationCreate,
    OrganizationOperatorService,
    OrganizationProjectAccessCreate,
    ResourceAssignmentCreate,
    SharedPartyCreate,
    SharedPartyType,
)
from construction_os.project_operator.signal_detection import (
    InMemoryProjectSignalRepository,
    ProjectSignal,
    ProjectSignalDetectionService,
    ProjectSignalStatus,
    ProjectSignalType,
    SignalSeverity,
)


async def _services() -> tuple[
    OrganizationOperatorService,
    InMemoryOrganizationOperatorRepository,
    OperationalStateService,
    InMemoryProjectSignalRepository,
]:
    state = OperationalStateService(InMemoryOperationalStateRepository())
    signal_repository = InMemoryProjectSignalRepository()
    signals = ProjectSignalDetectionService(state, signal_repository)
    organization_repository = InMemoryOrganizationOperatorRepository()
    service = OrganizationOperatorService(
        organization_repository,
        state,
        signals,
    )
    return service, organization_repository, state, signal_repository


async def _evidence(
    state: OperationalStateService,
    project_id: str,
    source_id: str,
    quote: str = "Supporting project evidence.",
) -> str:
    evidence = await state.create_evidence(
        project_id,
        EvidenceCreate(
            source_id=source_id,
            source_type="project_document",
            quoted_text=quote,
        ),
    )
    return evidence.id


def _signal(
    project_id: str,
    signal_id: str,
    evidence_id: str,
    *,
    signal_type: ProjectSignalType = ProjectSignalType.DEPENDENCY_RISK,
    severity: SignalSeverity = SignalSeverity.HIGH,
) -> ProjectSignal:
    now = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
    return ProjectSignal(
        id=signal_id,
        project_id=project_id,
        signal_type=signal_type,
        severity=severity,
        summary=f"Operational signal for {project_id}",
        why_it_matters="This may affect the project schedule or coordination.",
        affected_entity_ids=[f"operator_record:{signal_id.split(':')[-1]}"],
        evidence_ids=[evidence_id],
        confidence=0.9,
        recommended_response="Assign an owner and confirm mitigation.",
        fingerprint=f"fingerprint-{signal_id}",
        status=ProjectSignalStatus.NEW,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_shared_parties_are_deduplicated_by_normalized_identity() -> None:
    service, repository, _state, _signals = await _services()
    organization = await service.create_organization(
        OrganizationCreate(name="Kealii Construction")
    )

    first = await service.register_party(
        organization.id,
        SharedPartyCreate(
            name="Acme Electric",
            party_type=SharedPartyType.SUBCONTRACTOR,
            email="BIDS@ACME.COM",
        ),
    )
    second = await service.register_party(
        organization.id,
        SharedPartyCreate(
            name="  ACME Electrical LLC  ",
            party_type=SharedPartyType.SUBCONTRACTOR,
            email="bids@acme.com",
        ),
    )

    assert second.id == first.id
    assert second.normalized_key == "subcontractor|bids@acme.com"
    assert len(await repository.list_parties(organization.id)) == 1


@pytest.mark.asyncio
async def test_overview_respects_project_visibility_and_preserves_provenance() -> None:
    service, _repository, state, signal_repository = await _services()
    organization = await service.create_organization(
        OrganizationCreate(name="Island Builders")
    )
    await service.add_project_access(
        organization.id,
        OrganizationProjectAccessCreate(
            project_id="project:alpha",
            can_view=True,
        ),
    )
    await service.add_project_access(
        organization.id,
        OrganizationProjectAccessCreate(
            project_id="project:hidden",
            can_view=False,
        ),
    )
    alpha_evidence = await _evidence(
        state,
        "project:alpha",
        "source:alpha-risk",
    )
    hidden_evidence = await _evidence(
        state,
        "project:hidden",
        "source:hidden-risk",
    )
    alpha_signal = await signal_repository.save(
        _signal(
            "project:alpha",
            "operator_signal:alpha-risk",
            alpha_evidence,
        )
    )
    await signal_repository.save(
        _signal(
            "project:hidden",
            "operator_signal:hidden-risk",
            hidden_evidence,
        )
    )

    overview = await service.build_overview(organization.id)

    assert overview.visible_project_ids == ["project:alpha"]
    assert len(overview.projects_at_risk) == 1
    insight = overview.projects_at_risk[0]
    assert insight.project_ids == ["project:alpha"]
    assert insight.source_signal_ids == [alpha_signal.id]
    assert insight.evidence_ids == [alpha_evidence]
    assert "project:hidden" not in insight.project_ids
    assert hidden_evidence not in insight.evidence_ids


@pytest.mark.asyncio
async def test_company_overview_is_read_only_and_projects_current_state() -> None:
    service, _repository, state, _signals = await _services()
    organization = await service.create_organization(
        OrganizationCreate(name="Project Portfolio")
    )
    for project_id in ["project:alpha", "project:beta"]:
        await service.add_project_access(
            organization.id,
            OrganizationProjectAccessCreate(project_id=project_id),
        )

    alpha_evidence = await _evidence(
        state,
        "project:alpha",
        "source:alpha-commitment",
    )
    beta_evidence = await _evidence(
        state,
        "project:beta",
        "source:beta-decision",
    )
    commitment = await state.create_record(
        "project:alpha",
        OperationalRecordCreate(
            record_type=OperationalRecordType.COMMITMENT,
            title="Deliver hood shop drawings",
            description="The shop drawings are due August 10.",
            status=OperationalStatus.ACTIVE,
            confidence=1.0,
            evidence_ids=[alpha_evidence],
            responsible_party_id="party:mechanical",
            attributes={"due_date": "2026-08-10T00:00:00+00:00"},
        ),
    )
    decision = await state.create_record(
        "project:beta",
        OperationalRecordCreate(
            record_type=OperationalRecordType.DECISION,
            title="Select dining room tile",
            description="Owner selection remains unresolved.",
            confidence=0.95,
            evidence_ids=[beta_evidence],
        ),
    )
    before_alpha = [
        item.model_dump(mode="json")
        for item in await state.list_records("project:alpha")
    ]
    before_beta = [
        item.model_dump(mode="json")
        for item in await state.list_records("project:beta")
    ]

    overview = await service.build_overview(organization.id)

    after_alpha = [
        item.model_dump(mode="json")
        for item in await state.list_records("project:alpha")
    ]
    after_beta = [
        item.model_dump(mode="json")
        for item in await state.list_records("project:beta")
    ]
    assert before_alpha == after_alpha
    assert before_beta == after_beta
    assert overview.commitments_due[0].record_id == commitment.id
    assert overview.commitments_due[0].responsible_party_id == "party:mechanical"
    assert overview.unresolved_decisions[0].source_record_ids == [decision.id]
    assert overview.unresolved_decisions[0].project_ids == ["project:beta"]


@pytest.mark.asyncio
async def test_overlapping_shared_resource_assignments_create_one_conflict() -> None:
    service, _repository, _state, _signals = await _services()
    organization = await service.create_organization(
        OrganizationCreate(name="Resource Portfolio")
    )
    for project_id in ["project:alpha", "project:beta", "project:hidden"]:
        await service.add_project_access(
            organization.id,
            OrganizationProjectAccessCreate(
                project_id=project_id,
                can_view=project_id != "project:hidden",
            ),
        )
    await service.assign_resource(
        organization.id,
        ResourceAssignmentCreate(
            resource_key="crew:electrical-one",
            resource_name="Electrical Crew 1",
            project_id="project:alpha",
            starts_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
            ends_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        ),
    )
    await service.assign_resource(
        organization.id,
        ResourceAssignmentCreate(
            resource_key="crew:electrical-one",
            resource_name="Electrical Crew 1",
            project_id="project:beta",
            starts_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            ends_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
        ),
    )
    await service.assign_resource(
        organization.id,
        ResourceAssignmentCreate(
            resource_key="crew:electrical-one",
            resource_name="Electrical Crew 1",
            project_id="project:hidden",
            starts_at=datetime(2026, 8, 5, tzinfo=timezone.utc),
            ends_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
        ),
    )

    overview = await service.build_overview(organization.id)

    assert len(overview.resource_conflicts) == 1
    assert overview.resource_conflicts[0].project_ids == [
        "project:alpha",
        "project:beta",
    ]


@pytest.mark.asyncio
async def test_repeated_party_issues_and_procurement_are_cross_project() -> None:
    service, _repository, state, _signals = await _services()
    organization = await service.create_organization(
        OrganizationCreate(name="Cross Project Operations")
    )
    record_ids: set[str] = set()
    for project_id in ["project:alpha", "project:beta"]:
        await service.add_project_access(
            organization.id,
            OrganizationProjectAccessCreate(project_id=project_id),
        )
        issue_evidence = await _evidence(
            state,
            project_id,
            f"source:{project_id}-issue",
        )
        procurement_evidence = await _evidence(
            state,
            project_id,
            f"source:{project_id}-procurement",
        )
        issue = await state.create_record(
            project_id,
            OperationalRecordCreate(
                record_type=OperationalRecordType.ISSUE,
                title="Late subcontractor response",
                description="A response remains overdue.",
                status=OperationalStatus.ACTIVE,
                confidence=0.9,
                evidence_ids=[issue_evidence],
                attributes={"party_id": "party:acme-electric"},
            ),
        )
        procurement = await state.create_record(
            project_id,
            OperationalRecordCreate(
                record_type=OperationalRecordType.REQUIREMENT,
                title="Purchase switchgear",
                description="Switchgear is required for the electrical scope.",
                status=OperationalStatus.ACTIVE,
                confidence=1.0,
                evidence_ids=[procurement_evidence],
                attributes={"procurement_key": "electrical-switchgear"},
            ),
        )
        record_ids.update({issue.id, procurement.id})

    overview = await service.build_overview(organization.id)

    assert len(overview.repeated_party_issues) == 1
    assert overview.repeated_party_issues[0].project_ids == [
        "project:alpha",
        "project:beta",
    ]
    assert len(overview.procurement_opportunities) == 1
    assert overview.procurement_opportunities[0].project_ids == [
        "project:alpha",
        "project:beta",
    ]
    projected_record_ids = set(
        overview.repeated_party_issues[0].source_record_ids
        + overview.procurement_opportunities[0].source_record_ids
    )
    assert projected_record_ids == record_ids


@pytest.mark.asyncio
async def test_company_actions_require_operate_access_and_org_approval_role() -> None:
    service, _repository, _state, _signals = await _services()
    organization = await service.create_organization(
        OrganizationCreate(
            name="Approval Portfolio",
            allowed_approval_roles=["executive"],
        )
    )
    await service.add_project_access(
        organization.id,
        OrganizationProjectAccessCreate(
            project_id="project:alpha",
            can_view=True,
            can_operate=True,
        ),
    )
    await service.add_project_access(
        organization.id,
        OrganizationProjectAccessCreate(
            project_id="project:beta",
            can_view=True,
            can_operate=False,
        ),
    )

    action = await service.propose_action(
        organization.id,
        OrganizationActionCreate(
            action_type=OrganizationActionType.REVIEW_COMPANY_RISK,
            title="Review project Alpha risk",
            reason="The project has multiple high-priority signals.",
            project_ids=["project:alpha"],
        ),
    )

    with pytest.raises(ValueError, match="cannot operate"):
        await service.propose_action(
            organization.id,
            OrganizationActionCreate(
                action_type=OrganizationActionType.RESOLVE_RESOURCE_CONFLICT,
                title="Resolve cross-project assignment",
                reason="The projects share an overlapping resource.",
                project_ids=["project:alpha", "project:beta"],
            ),
        )

    with pytest.raises(ValueError, match="approval policy"):
        await service.decide_action(
            organization.id,
            action.id,
            OrganizationActionDecision(
                actor_id="user:project-manager",
                actor_role="project_manager",
                approved=True,
            ),
        )

    approved = await service.decide_action(
        organization.id,
        action.id,
        OrganizationActionDecision(
            actor_id="user:executive",
            actor_role="executive",
            approved=True,
            reason="Company-level review is authorized.",
        ),
    )

    assert approved.status == OrganizationActionStatus.APPROVED
    assert approved.decided_by == "user:executive"
    assert approved.decided_role == "executive"
    assert approved.decision_reason == "Company-level review is authorized."
