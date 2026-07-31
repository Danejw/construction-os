from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.routers.project_operator import router
from construction_os.project_operator.operational_state import (
    EvidenceCreate,
    InMemoryOperationalStateRepository,
    OperationalRecordCreate,
    OperationalRecordType,
    OperationalStateService,
    OperationalStatus,
)


@pytest.mark.asyncio
async def test_record_requires_evidence_from_same_project() -> None:
    service = OperationalStateService(InMemoryOperationalStateRepository())
    evidence = await service.create_evidence(
        "project:alpha",
        EvidenceCreate(
            source_id="source:one",
            source_type="email",
            quoted_text="Plans will be ready Friday.",
        ),
    )

    with pytest.raises(ValueError, match="unavailable for this project"):
        await service.create_record(
            "project:beta",
            OperationalRecordCreate(
                record_type=OperationalRecordType.COMMITMENT,
                title="Plans delivery",
                description="Architect will deliver plans Friday.",
                confidence=0.9,
                evidence_ids=[evidence.id],
            ),
        )


@pytest.mark.asyncio
async def test_state_can_be_filtered_by_type_and_status() -> None:
    service = OperationalStateService(InMemoryOperationalStateRepository())
    evidence = await service.create_evidence(
        "project:alpha",
        EvidenceCreate(
            source_id="source:schedule",
            source_type="pdf",
            page_number=4,
            quoted_text="Submit hood shop drawings by August 12.",
        ),
    )
    commitment = await service.create_record(
        "project:alpha",
        OperationalRecordCreate(
            record_type=OperationalRecordType.COMMITMENT,
            title="Hood shop drawings",
            description="Shop drawings are due August 12.",
            status=OperationalStatus.ACTIVE,
            confidence=1.0,
            evidence_ids=[evidence.id],
            valid_from=datetime(2026, 7, 31, tzinfo=timezone.utc),
        ),
    )
    await service.create_record(
        "project:alpha",
        OperationalRecordCreate(
            record_type=OperationalRecordType.RISK,
            title="Potential procurement delay",
            description="Late drawings could delay hood procurement.",
            confidence=0.7,
            evidence_ids=[evidence.id],
        ),
    )

    results = await service.list_records(
        "project:alpha",
        OperationalRecordType.COMMITMENT,
        OperationalStatus.ACTIVE,
    )

    assert [item.id for item in results] == [commitment.id]
    assert results[0].evidence_ids == [evidence.id]


def test_evidence_requires_precise_location() -> None:
    with pytest.raises(ValidationError, match="precise source location"):
        EvidenceCreate(source_id="source:one", source_type="pdf")


def test_proposed_content_cannot_be_labeled_as_fact() -> None:
    with pytest.raises(ValidationError, match="facts must be explicitly"):
        OperationalRecordCreate(
            record_type=OperationalRecordType.FACT,
            title="Unconfirmed date",
            description="A possible date mentioned in an email.",
            confidence=0.5,
            evidence_ids=["operator_evidence:test"],
        )


def test_operational_state_api_round_trip() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    project_id = "project:state-api"

    evidence_response = client.post(
        f"/api/projects/{project_id}/operator/evidence",
        json={
            "source_id": "source:email-one",
            "source_type": "email",
            "quoted_text": "The grease interceptor lead time is six weeks.",
        },
    )
    assert evidence_response.status_code == 200
    evidence_id = evidence_response.json()["id"]

    record_response = client.post(
        f"/api/projects/{project_id}/operator/state",
        json={
            "record_type": "risk",
            "title": "Grease interceptor lead time",
            "description": "A six-week lead time may affect excavation sequencing.",
            "status": "proposed",
            "confidence": 0.82,
            "evidence_ids": [evidence_id],
        },
    )
    assert record_response.status_code == 200
    assert record_response.json()["evidence_ids"] == [evidence_id]

    list_response = client.get(
        f"/api/projects/{project_id}/operator/state?record_type=risk&status=proposed"
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
