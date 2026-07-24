"""Unit tests for knowledge graph helpers."""

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import commands.knowledge_graph_commands as kg_commands
from construction_os.domain.knowledge_graph import normalize_entity_key
from construction_os.knowledge.extractors.base import (
    ExtractedClaim,
    ExtractedEntity,
    ExtractedRelation,
    ExtractionPayload,
)
from construction_os.knowledge.extractors.parse import (
    extract_json_object,
    extraction_is_empty,
    extraction_missing_expected_relations,
    merge_extraction_payloads,
    parse_extraction_payload,
    relations_warning_stats,
    split_text_windows,
    stats_have_graph_content,
)
from construction_os.knowledge.extractors.bootstrap import bootstrap_entities
from construction_os.knowledge.extractors.crossrefs import (
    count_detected_callouts,
    extract_crossrefs,
    merge_with_deterministic_crossrefs,
)
from construction_os.knowledge.extractors.enrich import (
    deterministic_sufficient,
    enrich_with_deterministic,
)
from construction_os.knowledge.extractors.registry import get_extractor, list_extractors
from construction_os.knowledge.extractors.select import (
    select_extractor_for_source,
    select_extractor_id,
)
from construction_os.knowledge.graph_projection import (
    _appears_in_edge,
    entity_source_ids,
)


@pytest.mark.asyncio
async def test_kg_no_projects_records_stage_failure(monkeypatch):
    source = MagicMock()
    source.id = "source:abc"
    source.full_text = "source text"
    source.content_hash = hashlib.sha256(b"source text").hexdigest()

    monkeypatch.setattr(kg_commands.Source, "get", AsyncMock(return_value=source))
    monkeypatch.setattr(kg_commands, "select_extractor_id", lambda **_kwargs: "generic")
    monkeypatch.setattr(
        kg_commands, "get_extractor", lambda _extractor: SimpleNamespace(version="1")
    )
    monkeypatch.setattr(
        kg_commands, "resolve_project_ids_for_source", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(kg_commands, "_fail_run", AsyncMock())
    monkeypatch.setattr(kg_commands, "set_pipeline_stage", AsyncMock())
    record_failure = AsyncMock()
    monkeypatch.setattr(kg_commands, "record_pipeline_failure", record_failure)

    with pytest.raises(ValueError, match="not linked"):
        await kg_commands.build_knowledge_graph_command(
            kg_commands.BuildKGInput(
                source_id="source:abc",
                extractor="generic",
                auto_select=False,
            )
        )

    record_failure.assert_awaited()
    assert record_failure.await_args.args[0:2] == (
        "source:abc",
        "knowledge_graph",
    )


@pytest.mark.asyncio
async def test_kg_unchanged_success_clears_stage_failure(monkeypatch):
    source = MagicMock()
    source.id = "source:abc"
    source.full_text = "source text"
    source.content_hash = hashlib.sha256(b"source text").hexdigest()

    monkeypatch.setattr(kg_commands.Source, "get", AsyncMock(return_value=source))
    monkeypatch.setattr(kg_commands, "select_extractor_id", lambda **_kwargs: "generic")
    monkeypatch.setattr(
        kg_commands, "get_extractor", lambda _extractor: SimpleNamespace(version="1")
    )
    monkeypatch.setattr(
        kg_commands,
        "resolve_project_ids_for_source",
        AsyncMock(return_value=["project:one"]),
    )
    monkeypatch.setattr(
        kg_commands,
        "repo_query",
        AsyncMock(return_value=[{"stats": {"entities": 1}}]),
    )
    monkeypatch.setattr(kg_commands, "set_pipeline_stage", AsyncMock())
    clear_failure = AsyncMock()
    monkeypatch.setattr(kg_commands, "clear_pipeline_failure", clear_failure)

    result = await kg_commands.build_knowledge_graph_command(
        kg_commands.BuildKGInput(
            source_id="source:abc",
            extractor="generic",
            auto_select=False,
        )
    )

    assert result.success is True
    assert result.skipped is True
    clear_failure.assert_awaited_once_with("source:abc", "knowledge_graph")


@pytest.mark.asyncio
async def test_kg_command_redacts_credentials_before_rethrow(monkeypatch):
    monkeypatch.setattr(
        kg_commands.Source,
        "get",
        AsyncMock(side_effect=RuntimeError("provider api_key=secret-value")),
    )
    monkeypatch.setattr(kg_commands, "record_pipeline_failure", AsyncMock())

    with pytest.raises(RuntimeError) as exc_info:
        await kg_commands.build_knowledge_graph_command(
            kg_commands.BuildKGInput(source_id="source:abc")
        )

    assert "secret-value" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_normalize_entity_key():
    assert normalize_entity_key("AHU-2") == "ahu 2"
    assert normalize_entity_key("  Room 201!! ") == "room 201"
    assert normalize_entity_key("09 30 00") == "09 30 00"


def test_extractor_registry():
    ids = {e["id"] for e in list_extractors()}
    assert ids == {"generic", "contract", "drawing", "spec", "email"}
    generic = get_extractor("generic")
    assert generic.auto_run is True
    assert get_extractor("drawing").auto_run is False


def test_extraction_payload_defaults():
    payload = ExtractionPayload()
    assert payload.entities == []
    assert payload.claims == []


def test_extract_json_object_from_fence():
    raw = 'Here you go:\n```json\n{"entities": [], "mentions": [], "claims": [], "relations": []}\n```\n'
    obj = extract_json_object(raw)
    assert obj.startswith("{")
    payload = parse_extraction_payload(raw)
    assert payload.entities == []


def test_extract_json_object_bare():
    raw = '{"entities":[{"label":"AHU-1","type":"Topic"}],"mentions":[],"claims":[],"relations":[]}'
    payload = parse_extraction_payload(raw)
    assert len(payload.entities) == 1
    assert payload.entities[0].label == "AHU-1"


def test_parse_extraction_payload_invalid_raises():
    with pytest.raises(ValueError, match="parse_failed"):
        parse_extraction_payload("not json at all")


@pytest.mark.asyncio
async def test_invoke_extractor_llm_uses_structured_outputs(monkeypatch):
    from construction_os.knowledge.extractors import parse as parse_mod

    expected = ExtractionPayload(
        entities=[ExtractedEntity(label="AHU-1", type="Topic")],
    )
    captured: dict = {}

    async def fake_invoke(messages, schema, **kwargs):
        captured["messages"] = messages
        captured["schema"] = schema
        captured["kwargs"] = kwargs
        assert "format_instructions" not in str(messages)
        assert "Output JSON only" not in str(messages)
        return expected

    monkeypatch.setattr(parse_mod, "invoke_structured", fake_invoke)
    payload = await parse_mod.invoke_extractor_llm(
        prompt_template="knowledge/generic_extract",
        text="AHU-1 is on sheet A-101.",
        source_id="source:1",
        project_id="project:1",
        chunk_count=1,
    )
    assert payload.entities[0].label == "AHU-1"
    assert captured["schema"] is ExtractionPayload


def test_split_text_windows_cap():
    text = "x" * 25000
    windows = split_text_windows(text, window_size=8000, overlap=500, max_windows=3)
    assert len(windows) == 3
    assert all(len(w) <= 8000 for w in windows)


def test_merge_extraction_payloads_dedupes():
    a = ExtractionPayload(
        entities=[ExtractedEntity(label="AHU-1", type="Topic")],
        claims=[
            ExtractedClaim(
                subject_label="AHU-1",
                predicate="LOCATED_IN",
                object_label="Room 201",
            )
        ],
        relations=[
            ExtractedRelation(
                type="REFERENCES",
                from_label="A-101",
                to_label="A-501",
            )
        ],
    )
    b = ExtractionPayload(
        entities=[
            ExtractedEntity(label="AHU-1", type="Topic"),
            ExtractedEntity(label="Room 201", type="Location"),
        ],
        claims=[
            ExtractedClaim(
                subject_label="AHU-1",
                predicate="LOCATED_IN",
                object_label="Room 201",
            )
        ],
        relations=[
            ExtractedRelation(
                type="REFERENCES",
                from_label="A-101",
                to_label="A-501",
            )
        ],
    )
    merged = merge_extraction_payloads([a, b])
    assert len(merged.entities) == 2
    assert len(merged.claims) == 1
    assert len(merged.relations) == 1


def test_extraction_is_empty_and_stats_gate():
    empty = ExtractionPayload()
    assert extraction_is_empty(empty) is True
    assert stats_have_graph_content({"entities": 0, "claims": 0, "relations": 0}) is False
    assert stats_have_graph_content({"entities": 2, "claims": 0, "relations": 0}) is True
    assert stats_have_graph_content(None) is False


def test_select_extractor_drawing_from_title():
    source = SimpleNamespace(
        title="Page_005_P201_Plumbing_Waste_Vent_Floor_Plan",
        asset=SimpleNamespace(file_path="plans/P201.pdf"),
    )
    assert select_extractor_for_source(source) == "drawing"


def test_select_extractor_spec_from_path():
    source = SimpleNamespace(
        title="Division 09 Finishes",
        asset={"file_path": "specs/section_09_30_00.md"},
    )
    assert select_extractor_for_source(source) == "spec"


def test_select_extractor_id_keeps_specialized():
    source = SimpleNamespace(title="anything", asset=None)
    assert (
        select_extractor_id(
            requested="contract", source=source, auto_select_generic=True
        )
        == "contract"
    )


def test_select_extractor_id_auto_upgrades_generic():
    source = SimpleNamespace(
        title="Sheet A-501 Details",
        asset=SimpleNamespace(file_path="A-501.dwg"),
    )
    assert (
        select_extractor_id(
            requested="generic", source=source, auto_select_generic=True
        )
        == "drawing"
    )
    assert (
        select_extractor_id(
            requested="generic", source=source, auto_select_generic=False
        )
        == "generic"
    )


def test_extract_crossrefs_see_detail_callout():
    text = "SHEET A-101 FLOOR PLAN\nSEE 3/A-501 FOR ENLARGED DETAIL\n"
    payload = extract_crossrefs(text)
    assert len(payload.relations) >= 1
    assert any(r.type == "REFERENCES" and "A-501" in r.to_label for r in payload.relations)
    assert any(e.label == "A-101" for e in payload.entities)
    assert count_detected_callouts(text) >= 1


def test_extract_crossrefs_unhyphenated_sheets_and_index():
    text = """---
sheet: P001
sheet_name: GENERAL NOTES
---
# Sheet P001 - Sheet index

| Sheet | Title |
|---|---|
| P001 | GENERAL NOTES, CODES & SHEET INDEX |
| P201 | PLUMBING WASTE / VENT FLOOR PLAN |
| P401 | PLUMBING DETAILS |

SEE SHEET P201 FOR FLOOR PLAN
"""
    payload = extract_crossrefs(text)
    labels = {e.label for e in payload.entities}
    assert "P001" in labels
    assert "P201" in labels
    assert "P401" in labels
    assert any(
        r.type == "REFERENCES" and r.from_label == "P001" and r.to_label == "P201"
        for r in payload.relations
    )
    assert count_detected_callouts(text) >= 1


def test_extract_crossrefs_csi_and_see_section():
    text = "Refer to Division finishes. See section 09 30 00 for tiling."
    payload = extract_crossrefs(text)
    assert any("09 30 00" in e.label for e in payload.entities)
    assert len(payload.relations) >= 1


def test_deterministic_sufficient_requires_relations():
    orphan_entities = ExtractionPayload(
        entities=[
            ExtractedEntity(label=f"E{i}", type="Topic") for i in range(8)
        ]
    )
    assert deterministic_sufficient(orphan_entities) is False

    with_rel = ExtractionPayload(
        entities=[
            ExtractedEntity(label="A-101", type="Reference"),
            ExtractedEntity(label="A-501", type="Reference"),
            ExtractedEntity(label="Topic", type="Topic"),
        ],
        relations=[
            ExtractedRelation(
                type="REFERENCES",
                from_label="A-101",
                from_type="Reference",
                to_label="A-501",
                to_type="Reference",
            )
        ],
    )
    assert deterministic_sufficient(with_rel) is True


def test_extract_crossrefs_co_document_sheet_edges():
    text = """---
sheet: P001
---
Notes mention P201 and P401 and section 09 30 00.
"""
    payload = extract_crossrefs(text)
    assert any(
        r.type == "REFERENCES" and r.from_label == "P001" and r.to_label == "P201"
        for r in payload.relations
    )
    assert any(
        r.type == "REFERENCES" and r.from_label == "P001" and r.to_label == "P401"
        for r in payload.relations
    )
    assert any(
        r.type == "REFERENCES"
        and r.from_label == "P001"
        and "09 30 00" in r.to_label
        for r in payload.relations
    )
    assert count_detected_callouts(text) == 0


def test_extract_crossrefs_ocr_callout_variants():
    text_no_space = "SHEET A-101\nSEE3/A501 FOR DETAIL\n"
    payload_no_space = extract_crossrefs(text_no_space)
    assert count_detected_callouts(text_no_space) >= 1
    assert any(
        r.type == "REFERENCES" and "A501" in r.to_label.replace("-", "")
        for r in payload_no_space.relations
    )

    text_sht = "sheet: P001\nSEE SHT P201 FOR PLAN\n"
    payload_sht = extract_crossrefs(text_sht)
    assert count_detected_callouts(text_sht) >= 1
    assert any(
        r.type == "REFERENCES" and r.to_label == "P201"
        for r in payload_sht.relations
    )


def test_bootstrap_entities_from_title_and_sheet_text():
    text = """---
sheet: A501
---
# Details
AHU-2 serves Room 201. DETAIL 3/A501.
"""
    payload = bootstrap_entities(
        text,
        title="Page_012_A501_Details",
        file_path="drawings/A501.pdf",
        topics=["mechanical"],
    )
    labels = {e.label for e in payload.entities}
    assert "A501" in labels or "A-501" in labels or any("A501" in x for x in labels)
    assert any("AHU" in e.label for e in payload.entities)
    assert any(e.type == "Location" for e in payload.entities)
    assert any(e.label == "mechanical" for e in payload.entities)
    assert len(payload.entities) >= 3


def test_enrich_with_deterministic_fills_empty_llm():
    empty = ExtractionPayload()
    text = "sheet: P001\n| P201 | FLOOR PLAN |\nSEE P401\n"
    merged = enrich_with_deterministic(
        empty, text, title="P001 General Notes", file_path="P001.md"
    )
    assert not extraction_is_empty(merged)
    assert len(merged.entities) >= 1
    assert len(merged.relations) >= 1


def test_merge_with_deterministic_crossrefs_keeps_llm_and_parser():
    llm = ExtractionPayload(
        entities=[ExtractedEntity(label="AHU-1", type="Topic")],
        relations=[],
    )
    text = "A-101 PLAN SEE A-501"
    merged = merge_with_deterministic_crossrefs(llm, text)
    assert any(e.label == "AHU-1" for e in merged.entities)
    assert len(merged.relations) >= 1


def test_extraction_missing_expected_relations_gate():
    text = "A-101 SEE 3/A-501"
    empty_rels = ExtractionPayload(
        entities=[ExtractedEntity(label="Topic X", type="Topic")]
    )
    assert extraction_missing_expected_relations(empty_rels, text, "drawing")
    assert extraction_missing_expected_relations(empty_rels, text, "generic") is None
    with_rels = extract_crossrefs(text)
    assert extraction_missing_expected_relations(with_rels, text, "drawing") is None


def test_relations_warning_stats():
    payload = ExtractionPayload(
        entities=[
            ExtractedEntity(label="a", type="Topic"),
            ExtractedEntity(label="b", type="Topic"),
            ExtractedEntity(label="c", type="Topic"),
        ]
    )
    assert relations_warning_stats(payload) == "entities_without_relations"
    assert relations_warning_stats(ExtractionPayload()) is None


def test_appears_in_edge_and_entity_source_ids():
    edge = _appears_in_edge("kg_entity:1", "source:abc")
    assert edge.relation == "APPEARS_IN"
    assert edge.id == "appears_in:kg_entity:1:source:abc"
    ids = entity_source_ids(
        {
            "source_id": "source:a",
            "metadata": {"MERGED_FROM": ["source:b", "source:a"]},
        }
    )
    assert ids == ["source:a", "source:b"]


def test_linker_extractor_constant():
    from construction_os.knowledge.project_linker import LINKER_EXTRACTOR

    assert LINKER_EXTRACTOR == "project_linker"
