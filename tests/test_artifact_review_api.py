"""Lightweight API tests for artifact factual review endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from construction_os.exceptions import InvalidInputError, NotFoundError


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def _mock_run(**overrides: object) -> MagicMock:
    run = MagicMock()
    run.id = "artifact_review_run:r1"
    run.note_id = "note:n1"
    run.project_id = "project:p1"
    run.status = "needs_review"
    run.command_id = "command:c1"
    run.findings = {"claims": [], "memory_findings": [], "truncated": False}
    run.summary = {"unsupported": 1}
    run.content_hash = "abc123"
    run.error_message = None
    run.started_at = datetime(2026, 7, 24, tzinfo=timezone.utc)
    run.finished_at = None
    for key, value in overrides.items():
        setattr(run, key, value)
    return run


def _mock_artifact(**overrides: object) -> MagicMock:
    artifact = MagicMock()
    artifact.id = "note:n1"
    artifact.title = "Artifact"
    artifact.content = "original content"
    artifact.artifact_kind = "manual"
    artifact.note_type = "manual"
    artifact.created = "2026-01-01T00:00:00Z"
    artifact.updated = "2026-01-01T00:00:00Z"
    for key, value in overrides.items():
        setattr(artifact, key, value)
    return artifact


@patch(
    "api.routers.project_artifacts.start_artifact_review",
    new_callable=AsyncMock,
)
def test_start_review_returns_run_and_command(mock_start, client):
    run = _mock_run(status="pending")
    mock_start.return_value = (run, "command:c1")

    response = client.post("/api/project-artifacts/note:n1/review")

    assert response.status_code == 200
    assert response.json() == {
        "run_id": "artifact_review_run:r1",
        "command_id": "command:c1",
        "status": "pending",
    }
    mock_start.assert_awaited_once_with("note:n1")


@patch(
    "api.routers.project_artifacts.start_artifact_review",
    new_callable=AsyncMock,
)
def test_start_review_missing_artifact_404(mock_start, client):
    mock_start.side_effect = NotFoundError("Artifact not found")

    response = client.post("/api/project-artifacts/note:gone/review")

    assert response.status_code == 404
    assert response.json()["detail"] == "Artifact not found"


@patch(
    "api.routers.project_artifacts.get_latest_run",
    new_callable=AsyncMock,
)
@patch(
    "api.routers.project_artifacts.ProjectArtifact.get",
    new_callable=AsyncMock,
)
@patch(
    "api.routers.project_artifacts.is_run_stale",
    return_value=False,
)
def test_get_latest_review(mock_stale, mock_get, mock_latest, client):
    mock_get.return_value = _mock_artifact()
    mock_latest.return_value = _mock_run()

    response = client.get("/api/project-artifacts/note:n1/review")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "artifact_review_run:r1"
    assert data["stale"] is False
    assert data["status"] == "needs_review"
    mock_stale.assert_called_once()


@patch(
    "api.routers.project_artifacts.apply_review_fixes",
    new_callable=AsyncMock,
)
def test_apply_review_stale_returns_409(mock_apply, client):
    mock_apply.side_effect = InvalidInputError(
        "Review run is stale; re-run review before applying fixes"
    )

    response = client.post(
        "/api/project-artifacts/note:n1/review/apply",
        json={"run_id": "artifact_review_run:r1", "finding_ids": ["c1"]},
    )

    assert response.status_code == 409
    assert "stale" in response.json()["detail"].lower()


@patch(
    "api.routers.project_artifacts.apply_review_fixes",
    new_callable=AsyncMock,
)
@patch(
    "api.routers.project_artifacts.project_artifact_to_dict",
)
def test_apply_review_success(mock_to_dict, mock_apply, client):
    artifact = _mock_artifact(content="fixed content")
    mock_apply.return_value = (artifact, ["missing span"])
    mock_to_dict.return_value = {
        "id": "note:n1",
        "title": "Artifact",
        "content": "fixed content",
        "artifact_kind": "manual",
        "note_type": "manual",
        "created": "2026-01-01T00:00:00Z",
        "updated": "2026-01-01T00:00:00Z",
        "command_id": None,
    }

    response = client.post(
        "/api/project-artifacts/note:n1/review/apply",
        json={"run_id": "artifact_review_run:r1", "finding_ids": ["c1"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifact"]["content"] == "fixed content"
    assert data["skipped_spans"] == ["missing span"]
