"""Unit tests for KG canonical ownership, merge policy, and integrity helpers."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from construction_os.domain.knowledge_graph import (
    PROJECT_WIDE_MERGE_TYPES,
    KnowledgeGraphRepository,
    entity_identity_key,
    entity_record_id_for_identity,
    merges_project_wide,
    normalize_entity_key,
    supporting_source_ids_from_entity,
)
from construction_os.knowledge.dedupe import (
    merge_supporting_sources_for_group,
    pick_survivor,
)
from construction_os.knowledge.integrity import (
    dangling_relation_queries,
    entity_still_has_support,
)


def test_project_wide_merge_types():
    assert merges_project_wide("Reference") is True
    assert merges_project_wide("Specification") is True
    assert merges_project_wide("Date") is True
    assert merges_project_wide("Person") is False
    assert merges_project_wide("Topic") is False
    assert merges_project_wide("Organization") is False
    assert "Reference" in PROJECT_WIDE_MERGE_TYPES


def test_supporting_source_ids_includes_primary_merged_and_supporting():
    entity = {
        "source_id": "source:a",
        "metadata": {
            "MERGED_FROM": ["source:b"],
            "supporting_sources": ["source:a", "source:c"],
        },
    }
    ids = supporting_source_ids_from_entity(entity)
    assert set(ids) == {"source:a", "source:b", "source:c"}
    assert ids[0] == "source:a"


def test_normalize_still_works_for_sheet_refs():
    assert normalize_entity_key("A-501") == "a 501"


def test_entity_identity_key_project_wide_ignores_source():
    a = entity_identity_key(
        project_id="project:1",
        entity_type="Reference",
        normalized_key="a 501",
        source_id="source:x",
    )
    b = entity_identity_key(
        project_id="project:1",
        entity_type="Reference",
        normalized_key="a 501",
        source_id="source:y",
    )
    assert a == b
    assert entity_record_id_for_identity(a).startswith("kg_entity:")


def test_entity_identity_key_source_scoped_includes_source():
    a = entity_identity_key(
        project_id="project:1",
        entity_type="Topic",
        normalized_key="hvac",
        source_id="source:x",
    )
    b = entity_identity_key(
        project_id="project:1",
        entity_type="Topic",
        normalized_key="hvac",
        source_id="source:y",
    )
    assert a != b


def test_pick_survivor_prefers_richer_then_older():
    older_rich = {
        "id": "kg_entity:1",
        "created": "2024-01-01",
        "source_id": "source:a",
        "metadata": {"supporting_sources": ["source:a", "source:b"]},
    }
    newer_thin = {
        "id": "kg_entity:2",
        "created": "2024-06-01",
        "source_id": "source:c",
        "metadata": {"supporting_sources": ["source:c"]},
    }
    assert pick_survivor([newer_thin, older_rich])["id"] == "kg_entity:1"


def test_merge_supporting_sources_for_group_unions():
    survivor = {
        "id": "kg_entity:1",
        "source_id": "source:a",
        "metadata": {"supporting_sources": ["source:a"]},
    }
    dup = {
        "id": "kg_entity:2",
        "source_id": "source:b",
        "metadata": {"MERGED_FROM": ["source:c"]},
    }
    meta = merge_supporting_sources_for_group(survivor, [dup])
    assert set(meta["supporting_sources"]) == {"source:a", "source:b", "source:c"}


def test_dangling_relation_queries_are_read_only():
    from_q, to_q = dangling_relation_queries()
    assert "NOT IN" in from_q
    assert "NOT IN" in to_q
    assert "DELETE" not in from_q.upper()
    assert "DELETE" not in to_q.upper()


def test_offsets_in_chunk_finds_span():
    from construction_os.knowledge.writer import (
        _offsets_in_chunk,
        find_chunk_index_for_text,
        find_text_offsets,
    )

    chunks = [{"id": "source_embedding:1", "content": "See detail 3/A-501 on plan."}]
    start, end = _offsets_in_chunk(chunks, 0, "3/A-501")
    assert start == 11
    assert end == 18
    assert find_text_offsets("See detail 3/A-501 on plan.", "3/A-501") == (11, 18)
    assert find_text_offsets("See DETAIL 3/A-501 here", "3/a-501") == (11, 18)
    assert find_chunk_index_for_text(chunks, "3/A-501") == 0
    # Curly apostrophe in source vs straight in mention (KG-014)
    curly = "Contractor\u2019s responsibility."
    assert find_text_offsets(curly, "Contractor's responsibility.")[0] is not None


def test_best_chunk_for_texts_prefers_both_labels():
    from construction_os.knowledge.backfill import _best_chunk_for_texts

    chunks = [
        {"id": "source_embedding:a", "content": "See A702 only."},
        {"id": "source_embedding:b", "content": "Detail 5/A401 refers to A702."},
    ]
    best = _best_chunk_for_texts(chunks, ["5/A401", "A702"])
    assert best is not None
    assert best["id"] == "source_embedding:b"
    assert best["hits"] == 2


def test_materialize_supporting_sources_metadata():
    from construction_os.knowledge.backfill import (
        _is_derived_relation,
        materialize_supporting_sources_metadata,
        needs_derived_flag,
    )

    entity = {
        "source_id": "source:a",
        "metadata": {"MERGED_FROM": ["source:b"]},
    }
    meta = materialize_supporting_sources_metadata(entity)
    assert meta is not None
    assert meta["supporting_sources"] == ["source:a", "source:b"]

    already = {
        "source_id": "source:a",
        "metadata": {
            "supporting_sources": ["source:a", "source:b"],
            "MERGED_FROM": ["source:b"],
        },
    }
    assert materialize_supporting_sources_metadata(already) is None

    assert needs_derived_flag({"extractor": "project_linker", "metadata": {}}) is True
    assert (
        needs_derived_flag(
            {"extractor": "project_linker", "metadata": {"derived": True}}
        )
        is False
    )
    assert needs_derived_flag({"extractor": "generic", "metadata": {}}) is False
    assert _is_derived_relation({"extractor": "project_linker", "metadata": {}}) is True
    assert (
        _is_derived_relation({"extractor": "generic", "metadata": {"derived": True}})
        is True
    )
    assert _is_derived_relation({"extractor": "generic", "metadata": {}}) is False


def test_graph_rag_mode_defaults_to_on(monkeypatch):
    monkeypatch.delenv("CONSTRUCTION_OS_GRAPH_RAG_MODE", raising=False)
    from construction_os.retrieval.evidence_retriever import get_graph_rag_mode

    assert get_graph_rag_mode() == "on"
    monkeypatch.setenv("CONSTRUCTION_OS_GRAPH_RAG_MODE", "off")
    assert get_graph_rag_mode() == "off"


def test_entity_still_has_support():
    assert entity_still_has_support(["source:a", "source:b"], removed="source:a") is True
    assert entity_still_has_support(["source:a"], removed="source:a") is False


@pytest.mark.asyncio
async def test_upsert_entity_passes_datetime_created():
    """SCHEMAFULL kg_entity.created is option<datetime>; strings are rejected."""
    record_id = entity_record_id_for_identity(
        entity_identity_key(
            project_id="project:1",
            entity_type="Topic",
            normalized_key="hvac",
            source_id="source:x",
        )
    )
    upsert = AsyncMock(return_value=[])
    saved_row = {
        "id": record_id,
        "type": "Topic",
        "label": "HVAC",
        "normalized_key": "hvac",
        "project_id": "project:1",
        "source_id": "source:x",
        "metadata": {"supporting_sources": ["source:x"]},
        "created": datetime(2026, 7, 22, 19, 25, 44),
    }

    with (
        patch.object(
            KnowledgeGraphRepository,
            "_find_entities_by_identity",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "construction_os.domain.knowledge_graph.repo_upsert",
            upsert,
        ),
        patch(
            "construction_os.domain.knowledge_graph.repo_query",
            new=AsyncMock(return_value=[saved_row]),
        ),
        patch(
            "construction_os.domain.base.repo_update",
            new=AsyncMock(return_value=[saved_row]),
        ),
    ):
        entity = await KnowledgeGraphRepository.upsert_entity(
            project_id="project:1",
            entity_type="Topic",
            label="HVAC",
            source_id="source:x",
        )

    upsert.assert_awaited_once()
    payload = upsert.await_args.args[2]
    assert isinstance(payload["created"], datetime)
    assert not isinstance(payload["created"], str)
    assert entity.id == record_id
