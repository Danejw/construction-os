"""Tests for architectural drawing extraction (opt-in pipeline)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from construction_os.drawing.config import (
    STATUS_COMPLETED,
    get_drawing_retrieval_mode,
    load_drawing_extraction_config,
)
from construction_os.drawing.deterministic import (
    classify_page_deterministic,
    extract_page_content,
)
from construction_os.drawing.normalize import normalize_and_dedupe
from construction_os.drawing.pdf_inspect import (
    compute_file_hash,
    inspect_pdf,
    open_pdf,
    resolve_source_pdf_path,
)
from construction_os.drawing.render import render_page_assets
from construction_os.drawing.semantic import build_semantic_records
from construction_os.drawing.types import BBox, DrawingItemDraft, pdf_to_norm
from construction_os.drawing.vision import (
    MockVisionClient,
    set_vision_client_override,
)

FIXTURE = Path(__file__).parent / "fixtures" / "Page_017_A204.pdf"


@pytest.fixture(autouse=True)
def _mock_vision():
    set_vision_client_override(MockVisionClient())
    yield
    set_vision_client_override(None)


def test_reject_non_pdf_path(tmp_path: Path):
    p = tmp_path / "notes.txt"
    p.write_text("hello")
    with pytest.raises(ValueError, match="not a PDF"):
        resolve_source_pdf_path(str(p))


def test_missing_original_file():
    with pytest.raises(FileNotFoundError):
        resolve_source_pdf_path("data/uploads/does-not-exist.pdf")


def test_missing_file_path():
    with pytest.raises(ValueError, match="no original"):
        resolve_source_pdf_path(None)


@pytest.mark.skipif(not FIXTURE.exists(), reason="A204 fixture PDF missing")
def test_born_digital_pdf_inspection():
    pages, meta = inspect_pdf(FIXTURE)
    assert meta["page_count"] == 1
    page = pages[0]
    assert page["page_kind"] == "born_digital"
    assert page["word_count"] > 100
    assert page["width"] > 0 and page["height"] > 0
    assert page["words"][0]["bbox_norm"]["x0"] >= 0
    assert page["words"][0]["bbox_norm"]["x1"] <= 1


@pytest.mark.skipif(not FIXTURE.exists(), reason="A204 fixture PDF missing")
def test_page_coordinate_normalization():
    pages, _ = inspect_pdf(FIXTURE)
    page = pages[0]
    w, h = page["width"], page["height"]
    bbox = BBox(x0=0, y0=0, x1=w / 2, y1=h / 2)
    norm = pdf_to_norm(bbox, w, h)
    assert abs(norm.x1 - 0.5) < 1e-6
    assert abs(norm.y1 - 0.5) < 1e-6


@pytest.mark.skipif(not FIXTURE.exists(), reason="A204 fixture PDF missing")
def test_page_render_generation(tmp_path: Path):
    doc = open_pdf(FIXTURE)
    try:
        assets = render_page_assets(
            doc[0],
            tmp_path / "page0",
            page_dpi=72,
            thumbnail_dpi=36,
            include_grid_crops=False,
        )
        assert Path(assets["render_path"]).exists()
        assert Path(assets["thumbnail_path"]).exists()
    finally:
        doc.close()


@pytest.mark.skipif(not FIXTURE.exists(), reason="A204 fixture PDF missing")
def test_a204_sheet_metadata_and_rooms():
    pages, _ = inspect_pdf(FIXTURE)
    evidence = pages[0]
    classification = classify_page_deterministic(
        evidence, filename=FIXTURE.name, source_title="A204"
    )
    assert classification.is_drawing is True
    assert classification.sheet_number == "A204"
    assert classification.sheet_title and "Finish" in classification.sheet_title
    assert "finish_plan" in classification.drawing_types or "floor_plan" in classification.drawing_types
    assert classification.discipline == "architectural"

    items, _rels, _unc = extract_page_content(evidence, classification, page_index=0)
    rooms = {
        str((i.properties or {}).get("room_number")): i
        for i in items
        if i.item_type == "room" and (i.properties or {}).get("room_number")
    }
    expected = {
        "100": ("Reception", 113),
        "101": ("Dining", 3035),
        "102": ("Prep", 354),
        "103": ("Bar", 180),
        "104": ("Dishwashing", 464),
        "105": ("Office", 51),
        "106": ("Freezer", 82),
        "107": ("Cooler", 144),
        "108": ("Communal", 322),
        "109": ("Mech", 88),
    }
    for num, (name_part, area) in expected.items():
        assert num in rooms, f"missing room {num}"
        props = rooms[num].properties or {}
        assert props.get("stated_area_sf") == area
        assert name_part.lower() in str(props.get("room_name") or "").lower()

    finish_tags = {
        str((i.properties or {}).get("tag") or i.label)
        for i in items
        if i.item_type == "finish"
    }
    for tag in ["QT", "QT-B", "PT-1", "PT-4", "PT-11", "PL-4", "PL-6", "SS", "W-CUR"]:
        assert tag in finish_tags, f"missing finish tag {tag}"

    refs = {
        str((i.properties or {}).get("referenced_sheet") or i.label)
        for i in items
        if i.subtype == "sheet_reference"
    }
    for ref in ["A201", "A401", "A402"]:
        assert ref in refs

    scale = next(
        (i for i in items if i.subtype == "scale"),
        None,
    )
    assert scale is not None
    assert "3/16" in str((scale.properties or {}).get("value") or "")

    revision = next((i for i in items if i.subtype == "revision_number"), None)
    assert revision is not None
    assert str((revision.properties or {}).get("value")) == "3"

    notes = [i for i in items if i.item_type == "note"]
    assert len(notes) >= 1

    legends = [i for i in items if i.subtype == "legend"]
    assert len(legends) >= 1

    fds = [i for i in items if i.subtype == "floor_drain"]
    assert len(fds) >= 1


def test_file_hash_stable(tmp_path: Path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    assert compute_file_hash(p) == compute_file_hash(p)


def test_normalize_dedupe_and_conflicts():
    items = [
        DrawingItemDraft(
            stable_id="room:101",
            item_type="room",
            label="Room 101",
            properties={"room_number": "101", "room_name": "Dining", "stated_area_sf": 3035},
            raw_text="Dining\n3,035 SF\n101",
            confidence=0.9,
        ),
        DrawingItemDraft(
            stable_id="room:101",
            item_type="room",
            label="Room 101",
            properties={"room_number": "101", "room_name": "Dining", "stated_area_sf": 3035},
            raw_text="Dining\n3,035 SF\n101",
            confidence=0.8,
        ),
    ]
    out, _rels, conflicts = normalize_and_dedupe(items, [])
    assert len(out) == 1
    assert conflicts == []


def test_semantic_records_created():
    from construction_os.drawing.types import PageClassification

    classification = PageClassification(
        is_drawing=True,
        discipline="architectural",
        sheet_number="A204",
        sheet_title="Finish Floor Plan",
        drawing_types=["finish_plan"],
        confidence=0.9,
    )
    items = [
        DrawingItemDraft(
            stable_id="meta:sheet_number",
            item_type="metadata_field",
            subtype="sheet_number",
            label="sheet_number",
            properties={"value": "A204"},
            confidence=0.9,
        ),
        DrawingItemDraft(
            stable_id="room:101",
            item_type="room",
            label="Room 101",
            properties={
                "room_number": "101",
                "room_name": "Dining Area",
                "stated_area_sf": 3035,
            },
            confidence=0.9,
        ),
    ]
    records = build_semantic_records(
        classification=classification, items=items, page_index=0
    )
    types = {r["record_type"] for r in records}
    assert "sheet" in types
    assert "room" in types


@pytest.mark.asyncio
async def test_extraction_run_creation_and_isolation():
    """Creating a drawing run must not touch source.full_text or embeddings."""
    created: List[Dict[str, Any]] = []

    async def fake_create(table: str, data: Dict[str, Any]):
        row = {"id": f"{table}:1", **data}
        created.append({"table": table, "data": data})
        return row

    async def fake_update(table: str, id: str, data: Dict[str, Any]):
        return {"id": id, **data}

    source = MagicMock()
    source.id = "source:1"
    source.title = "A204"
    source.full_text = "ORIGINAL FULL TEXT MUST STAY"
    source.asset = MagicMock(file_path=str(FIXTURE) if FIXTURE.exists() else None)

    if not FIXTURE.exists():
        pytest.skip("A204 fixture missing")

    with (
        patch("construction_os.drawing.pipeline.Source.get", new=AsyncMock(return_value=source)),
        patch("construction_os.drawing.repository.repo_create", side_effect=fake_create),
        patch("construction_os.drawing.repository.repo_update", side_effect=fake_update),
        patch(
            "construction_os.drawing.repository.find_completed_run_by_hash",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "construction_os.drawing.repository.activate_run",
            new=AsyncMock(return_value={"id": "drawing_extraction_run:1", "active": True}),
        ),
        patch(
            "construction_os.drawing.pipeline.publish_drawing_embeddings",
            new=AsyncMock(return_value={"embedded": 0}),
        ),
        patch(
            "construction_os.drawing.pipeline.publish_drawing_knowledge_graph",
            new=AsyncMock(return_value={}),
        ),
        patch("construction_os.drawing.pipeline.repo_update", new=AsyncMock()),
    ):
        from construction_os.drawing.config import DrawingExtractionConfig
        from construction_os.drawing.pipeline import run_drawing_extraction

        cfg = load_drawing_extraction_config()
        cfg = DrawingExtractionConfig(
            **{
                **cfg.__dict__,
                "use_vision": False,
                "publish_embeddings": False,
                "publish_knowledge_graph": False,
            }
        )
        result = await run_drawing_extraction(
            source_id="source:1",
            project_id="project:1",
            force=True,
            publish=False,
            config=cfg,
        )

    assert result["success"] is True
    assert result["status"] in {STATUS_COMPLETED, "partial"}
    assert source.full_text == "ORIGINAL FULL TEXT MUST STAY"
    tables = {c["table"] for c in created}
    assert "drawing_extraction_run" in tables
    assert "drawing_page" in tables
    assert "source_embedding" not in tables
    assert "kg_entity" not in tables


@pytest.mark.asyncio
async def test_api_rejects_non_pdf(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routers import drawing_extraction

    app = FastAPI()
    app.include_router(drawing_extraction.router, prefix="/api")

    source = MagicMock()
    source.asset = MagicMock(file_path="data/uploads/note.txt")

    async def fake_get(_id: str):
        return source

    monkeypatch.setattr(drawing_extraction.Source, "get", fake_get)

    client = TestClient(app)
    resp = client.post(
        "/api/drawing-extractions/extract",
        json={"source_ids": ["source:1"], "project_id": "project:1"},
    )
    assert resp.status_code == 400


def test_drawing_retrieval_mode_default(monkeypatch):
    monkeypatch.delenv("CONSTRUCTION_OS_DRAWING_RAG_MODE", raising=False)
    assert get_drawing_retrieval_mode() == "off"


def test_drawing_retrieval_modes(monkeypatch):
    monkeypatch.setenv("CONSTRUCTION_OS_DRAWING_RAG_MODE", "shadow")
    assert get_drawing_retrieval_mode() == "shadow"
    monkeypatch.setenv("CONSTRUCTION_OS_DRAWING_RAG_MODE", "on")
    assert get_drawing_retrieval_mode() == "on"


@pytest.mark.asyncio
async def test_retrieval_off_ignores_drawing(monkeypatch):
    from construction_os.drawing.retrieval import maybe_merge_drawing_evidence
    from construction_os.retrieval.types import EvidenceItem

    monkeypatch.setenv("CONSTRUCTION_OS_DRAWING_RAG_MODE", "off")
    base = [
        EvidenceItem(id="1", score=0.9, content="doc", source="vector"),
    ]
    with patch(
        "construction_os.drawing.retrieval.retrieve_drawing_evidence",
        new=AsyncMock(
            return_value=[
                EvidenceItem(id="d1", score=0.95, content="drawing", source="drawing")
            ]
        ),
    ):
        items, note = await maybe_merge_drawing_evidence(
            query="room 101",
            project_id="project:1",
            existing_items=base,
            limit=10,
        )
    assert len(items) == 1
    assert items[0].id == "1"
    assert note is None


@pytest.mark.asyncio
async def test_retrieval_shadow_logs_but_does_not_merge(monkeypatch):
    from construction_os.drawing.retrieval import maybe_merge_drawing_evidence
    from construction_os.retrieval.types import EvidenceItem

    monkeypatch.setenv("CONSTRUCTION_OS_DRAWING_RAG_MODE", "shadow")
    base = [EvidenceItem(id="1", score=0.9, content="doc", source="vector")]
    with patch(
        "construction_os.drawing.retrieval.retrieve_drawing_evidence",
        new=AsyncMock(
            return_value=[
                EvidenceItem(id="d1", score=0.95, content="drawing", source="drawing")
            ]
        ),
    ):
        items, note = await maybe_merge_drawing_evidence(
            query="A204",
            project_id="project:1",
            existing_items=base,
            limit=10,
        )
    assert [i.id for i in items] == ["1"]
    assert note == "drawing_shadow_mode"


@pytest.mark.asyncio
async def test_retrieval_on_merges(monkeypatch):
    from construction_os.drawing.retrieval import maybe_merge_drawing_evidence
    from construction_os.retrieval.types import EvidenceItem

    monkeypatch.setenv("CONSTRUCTION_OS_DRAWING_RAG_MODE", "on")
    base = [EvidenceItem(id="1", score=0.9, content="doc", source="vector")]
    with patch(
        "construction_os.drawing.retrieval.retrieve_drawing_evidence",
        new=AsyncMock(
            return_value=[
                EvidenceItem(
                    id="d1",
                    score=0.95,
                    content="drawing",
                    source="drawing",
                    raw={"extraction_confidence": 0.9},
                )
            ]
        ),
    ):
        items, note = await maybe_merge_drawing_evidence(
            query="dining area",
            project_id="project:1",
            existing_items=base,
            limit=10,
        )
    assert {i.id for i in items} == {"1", "d1"}
    assert note is None


@pytest.mark.skipif(
    not FIXTURE.exists() or not __import__("os").getenv("CONSTRUCTION_OS_DRAWING_LIVE_TEST"),
    reason="Opt-in live A204 integration test (set CONSTRUCTION_OS_DRAWING_LIVE_TEST=1)",
)
@pytest.mark.asyncio
async def test_live_a204_with_vision():
    """Opt-in: runs real vision when credentials available."""
    set_vision_client_override(None)

    # This still needs DB; skip if not configured
    pytest.skip("Live DB+vision path exercised manually against local stack")
