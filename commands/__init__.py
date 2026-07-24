"""Surreal-commands integration for Construction OS"""

from .artifact_review_commands import review_artifact_command
from .chat_queue_commands import drain_chat_queue_command
from .drawing_commands import extract_architectural_drawings_command
from .embedding_commands import (
    embed_note_command,
    embed_source_command,
    rebuild_embeddings_command,
)
from .knowledge_graph_commands import build_knowledge_graph_command
from .podcast_commands import generate_podcast_command
from .project_memory_commands import consolidate_project_memory_command
from .source_commands import (
    ingest_text_source_command,
    process_source_command,
)

__all__ = [
    # Artifact factual review
    "review_artifact_command",
    # Persistent chat queue
    "drain_chat_queue_command",
    # Drawing extraction
    "extract_architectural_drawings_command",
    # Embedding commands
    "embed_note_command",
    "embed_source_command",
    "rebuild_embeddings_command",
    # Knowledge graph
    "build_knowledge_graph_command",
    # Project memory
    "consolidate_project_memory_command",
    # Other commands
    "generate_podcast_command",
    "process_source_command",
    "ingest_text_source_command",
]
