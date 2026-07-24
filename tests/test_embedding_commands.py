from unittest.mock import AsyncMock, MagicMock

import pytest
from surreal_commands import registry

import commands.embedding_commands as embedding_commands
from construction_os.exceptions import ConfigurationError
from construction_os.utils.chunking import TextChunk


def _plain_chunks(*texts: str) -> list[TextChunk]:
    """Build TextChunk fixtures matching chunk_text's return shape."""
    chunks: list[TextChunk] = []
    cursor = 0
    for text in texts:
        end = cursor + len(text)
        chunks.append(TextChunk(content=text, char_start=cursor, char_end=end))
        cursor = end
    return chunks


def test_legacy_embedding_commands_are_registered():
    app_commands = registry.list_commands()["construction_os"]

    assert "embed_chunk" in app_commands
    assert "embed_single_item" in app_commands
    assert "vectorize_source" in app_commands


@pytest.mark.asyncio
async def test_legacy_embed_chunk_processes_stale_queue_payload(monkeypatch):
    mock_generate_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
    mock_repo_query = AsyncMock()

    monkeypatch.setattr(
        embedding_commands, "generate_embedding", mock_generate_embedding
    )
    monkeypatch.setattr(embedding_commands, "repo_query", mock_repo_query)
    monkeypatch.setattr(
        embedding_commands, "ensure_record_id", lambda value: f"record:{value}"
    )

    result = await embedding_commands.legacy_embed_chunk_command(
        embedding_commands.LegacyEmbedChunkInput(
            source_id="source:abc",
            chunk_index=2,
            chunk_text="queued legacy chunk",
        )
    )

    assert result.success is True
    assert result.source_id == "source:abc"
    assert result.chunk_index == 2
    mock_generate_embedding.assert_awaited_once_with(
        "queued legacy chunk",
        content_type=embedding_commands.ContentType.PLAIN,
        command_id="unknown",
    )
    mock_repo_query.assert_awaited_once()
    assert mock_repo_query.await_args is not None
    assert mock_repo_query.await_args.args[1] == {
        "source_id": "record:source:abc",
        "order": 2,
        "content": "queued legacy chunk",
        "embedding": [0.1, 0.2, 0.3],
    }


@pytest.mark.asyncio
async def test_legacy_vectorize_source_delegates_to_embed_source(monkeypatch):
    async def fake_embed_source(input_data):
        assert input_data.source_id == "source:abc"
        return embedding_commands.EmbedSourceOutput(
            success=True,
            source_id=input_data.source_id,
            chunks_created=3,
            processing_time=0.1,
        )

    monkeypatch.setattr(embedding_commands, "embed_source_command", fake_embed_source)

    result = await embedding_commands.legacy_vectorize_source_command(
        embedding_commands.LegacyVectorizeSourceInput(source_id="source:abc")
    )

    assert result.success is True
    assert result.source_id == "source:abc"
    assert result.total_chunks == 3
    assert result.jobs_submitted == 1


@pytest.mark.asyncio
async def test_embed_source_runtime_error_fails_pipeline_without_raise(monkeypatch):
    source = MagicMock()
    source.full_text = "hello world"
    source.asset = None

    fail_pipeline = AsyncMock()
    record_failure = AsyncMock()
    monkeypatch.setattr(embedding_commands, "fail_pipeline", fail_pipeline)
    monkeypatch.setattr(
        embedding_commands, "record_pipeline_failure", record_failure
    )
    monkeypatch.setattr(
        embedding_commands.Source, "get", AsyncMock(return_value=source)
    )
    monkeypatch.setattr(
        embedding_commands, "detect_content_type", lambda *_a, **_k: embedding_commands.ContentType.PLAIN
    )
    monkeypatch.setattr(embedding_commands, "chunk_text", lambda *_a, **_k: _plain_chunks("hello world"))
    monkeypatch.setattr(
        embedding_commands,
        "generate_embeddings",
        AsyncMock(side_effect=RuntimeError("provider down api_key=secret-value")),
    )
    monkeypatch.setattr(embedding_commands, "repo_query", AsyncMock())
    monkeypatch.setattr(embedding_commands, "repo_insert", AsyncMock())
    monkeypatch.setattr(embedding_commands, "begin_kg_stage", AsyncMock())

    result = await embedding_commands.embed_source_command(
        embedding_commands.EmbedSourceInput(source_id="source:abc")
    )

    assert result.success is False
    assert "provider down" in (result.error_message or "")
    assert "secret-value" not in (result.error_message or "")
    assert result.error_type == "RuntimeError"
    assert result.completed_at
    fail_pipeline.assert_awaited_once_with("source:abc")
    record_failure.assert_awaited_once()
    assert record_failure.await_args.args[:3] == (
        "source:abc",
        "embedding",
        record_failure.await_args.args[2],
    )
    assert isinstance(record_failure.await_args.args[2], RuntimeError)


@pytest.mark.asyncio
async def test_embed_source_configuration_error_fails_pipeline(monkeypatch):
    source = MagicMock()
    source.full_text = "hello world"
    source.asset = None

    fail_pipeline = AsyncMock()
    monkeypatch.setattr(embedding_commands, "fail_pipeline", fail_pipeline)
    monkeypatch.setattr(
        embedding_commands.Source, "get", AsyncMock(return_value=source)
    )
    monkeypatch.setattr(
        embedding_commands, "detect_content_type", lambda *_a, **_k: embedding_commands.ContentType.PLAIN
    )
    monkeypatch.setattr(embedding_commands, "chunk_text", lambda *_a, **_k: _plain_chunks("hello world"))
    monkeypatch.setattr(
        embedding_commands,
        "generate_embeddings",
        AsyncMock(side_effect=ConfigurationError("bad model")),
    )

    result = await embedding_commands.embed_source_command(
        embedding_commands.EmbedSourceInput(source_id="source:abc")
    )

    assert result.success is False
    fail_pipeline.assert_awaited_once_with("source:abc")


@pytest.mark.asyncio
async def test_embed_source_success_begins_kg(monkeypatch):
    source = MagicMock()
    source.full_text = "hello world"
    source.asset = None

    begin_kg = AsyncMock(return_value="command:kg")
    clear_failure = AsyncMock()
    monkeypatch.setattr(embedding_commands, "begin_kg_stage", begin_kg)
    monkeypatch.setattr(embedding_commands, "clear_pipeline_failure", clear_failure)
    monkeypatch.setattr(
        embedding_commands.Source, "get", AsyncMock(return_value=source)
    )
    monkeypatch.setattr(
        embedding_commands, "detect_content_type", lambda *_a, **_k: embedding_commands.ContentType.PLAIN
    )
    monkeypatch.setattr(embedding_commands, "chunk_text", lambda *_a, **_k: _plain_chunks("hello world"))
    monkeypatch.setattr(
        embedding_commands,
        "generate_embeddings",
        AsyncMock(return_value=[[0.1, 0.2]]),
    )
    monkeypatch.setattr(embedding_commands, "repo_query", AsyncMock())
    monkeypatch.setattr(embedding_commands, "repo_insert", AsyncMock())
    monkeypatch.setattr(
        embedding_commands,
        "resolve_project_ids_for_source",
        AsyncMock(return_value=["project:1"]),
    )

    result = await embedding_commands.embed_source_command(
        embedding_commands.EmbedSourceInput(source_id="source:abc")
    )

    assert result.success is True
    assert result.chunks_created == 1
    begin_kg.assert_awaited_once_with("source:abc", ["project:1"])
    clear_failure.assert_awaited_once_with("source:abc", "embedding")


@pytest.mark.asyncio
async def test_rebuild_sources_uses_linked_embed_stage(monkeypatch):
    monkeypatch.setattr(
        embedding_commands.model_manager,
        "get_embedding_model",
        AsyncMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        embedding_commands,
        "collect_items_for_rebuild",
        AsyncMock(
            return_value={
                "sources": ["source:one", "source:two"],
                "notes": [],
            }
        ),
    )
    begin_embed = AsyncMock(side_effect=["command:one", "command:two"])
    monkeypatch.setattr(embedding_commands, "begin_embed_stage", begin_embed)

    result = await embedding_commands.rebuild_embeddings_command(
        embedding_commands.RebuildEmbeddingsInput(
            mode="all",
            include_sources=True,
            include_notes=False,
        )
    )

    assert result.success is True
    assert result.sources_submitted == 2
    assert begin_embed.await_count == 2
    begin_embed.assert_any_await("source:one", chain_kg=False)
    begin_embed.assert_any_await("source:two", chain_kg=False)


@pytest.mark.asyncio
async def test_rebuild_sources_can_opt_in_to_kg_chain(monkeypatch):
    """RAG-008: rebuild defaults to chain_kg=False; operators can opt in."""
    monkeypatch.setattr(
        embedding_commands.model_manager,
        "get_embedding_model",
        AsyncMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        embedding_commands,
        "collect_items_for_rebuild",
        AsyncMock(
            return_value={
                "sources": ["source:one"],
                "notes": [],
            }
        ),
    )
    begin_embed = AsyncMock(return_value="command:one")
    monkeypatch.setattr(embedding_commands, "begin_embed_stage", begin_embed)

    result = await embedding_commands.rebuild_embeddings_command(
        embedding_commands.RebuildEmbeddingsInput(
            mode="existing",
            include_sources=True,
            include_notes=False,
            chain_kg=True,
        )
    )

    assert result.success is True
    begin_embed.assert_awaited_once_with("source:one", chain_kg=True)


@pytest.mark.asyncio
async def test_legacy_embed_single_item_routes_notes(monkeypatch):
    async def fake_embed_note(input_data):
        assert input_data.note_id == "note:abc"
        return embedding_commands.EmbedNoteOutput(
            success=True,
            note_id=input_data.note_id,
            processing_time=0.1,
        )

    monkeypatch.setattr(embedding_commands, "embed_note_command", fake_embed_note)

    result = await embedding_commands.legacy_embed_single_item_command(
        embedding_commands.LegacyEmbedSingleItemInput(
            item_id="note:abc",
            item_type="note",
        )
    )

    assert result.success is True
    assert result.item_id == "note:abc"
    assert result.item_type == "note"
    assert result.chunks_created == 0
