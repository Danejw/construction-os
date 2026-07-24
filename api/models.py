from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Project models
class ProjectCreate(BaseModel):
    name: str = Field(..., description="Name of the Project")
    description: str = Field(default="", description="Description of the Project")


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Name of the Project")
    description: Optional[str] = Field(None, description="Description of the Project")
    archived: Optional[bool] = Field(
        None, description="Whether the Project is archived"
    )


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    archived: bool
    created: str
    updated: str
    source_count: int
    note_count: int


class ProjectMemoryResponse(BaseModel):
    project_id: str
    content: str
    evidence_ids: List[str] = Field(default_factory=list)
    revision: int = 0
    last_reason: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProjectMemoryUpdate(BaseModel):
    content: str = Field(..., description="Synthesized project memory markdown")


# Search models
class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    type: Literal["text", "vector", "hybrid", "auto"] = Field(
        "auto",
        description=(
            "Search type (default 'auto', same retrieve() heuristics as project chat): "
            "'auto' = retrieve(mode='auto') — hybrid for identifier-style queries, "
            "else vector; optional graph when CONSTRUCTION_OS_GRAPH_RAG_MODE=on; "
            "'hybrid' = BM25 + vector via RRF; "
            "'vector' = dense similarity only (no keyword fusion); "
            "'text' = keyword/BM25 only. "
            "Use vector/text only when that mode is intentional."
        ),
    )
    limit: int = Field(100, description="Maximum number of results", ge=1, le=1000)
    search_sources: bool = Field(True, description="Include sources in search")
    search_artifacts: Optional[bool] = Field(
        None, description="Include project artifacts in search (canonical)"
    )
    search_notes: bool = Field(
        True, description="Deprecated alias for search_artifacts"
    )
    minimum_score: float = Field(
        0.2, description="Minimum score for vector search", ge=0, le=1
    )
    project_id: Optional[str] = Field(
        None,
        description=(
            "Optional project scope; when set, only project members are searched. "
            "When omitted, search is corpus-wide — intentional for single-tenant "
            "deployments (RAG-009 accepted)."
        ),
    )

    def resolve_search_artifacts(self) -> bool:
        if self.search_artifacts is not None:
            return self.search_artifacts
        return self.search_notes


class SearchResponse(BaseModel):
    results: List[Dict[str, Any]] = Field(..., description="Search results")
    total_count: int = Field(..., description="Total number of results")
    search_type: str = Field(..., description="Requested search type")
    retrieval_mode_used: Optional[str] = Field(
        None,
        description=(
            "Actual retrieve() mode used when type is hybrid or auto "
            "(e.g. vector, hybrid, graph); null for text/vector"
        ),
    )
    embedding_dim_warning: Optional[str] = Field(
        None,
        description=(
            "Present when indexed embedding dimensions drift from the active model; "
            "rebuild embeddings to restore vector recall"
        ),
    )


# Models API models
class ModelCreate(BaseModel):
    name: str = Field(..., description="Model name (e.g., gpt-5-mini, claude, gemini)")
    provider: str = Field(
        ..., description="Provider name (e.g., openai, anthropic, gemini)"
    )
    type: str = Field(
        ...,
        description="Model type (language, embedding, text_to_speech, speech_to_text)",
    )
    credential: Optional[str] = Field(
        None, description="Credential ID to link this model to"
    )


class ModelResponse(BaseModel):
    id: str
    name: str
    provider: str
    type: str
    credential: Optional[str] = None
    created: str
    updated: str


class DefaultModelsResponse(BaseModel):
    default_chat_model: Optional[str] = None
    default_artifact_model: Optional[str] = None
    large_context_model: Optional[str] = None
    default_text_to_speech_model: Optional[str] = None
    default_speech_to_text_model: Optional[str] = None
    default_embedding_model: Optional[str] = None
    default_tools_model: Optional[str] = None


class ProviderAvailabilityResponse(BaseModel):
    available: List[str] = Field(..., description="List of available providers")
    unavailable: List[str] = Field(..., description="List of unavailable providers")
    supported_types: Dict[str, List[str]] = Field(
        ..., description="Provider to supported model types mapping"
    )


# artifacts API models
class ArtifactCreate(BaseModel):
    name: str = Field(..., description="Artifact name")
    title: str = Field(..., description="Display title for the Artifact")
    description: str = Field(..., description="Description of what this Artifact does")
    prompt: str = Field(..., description="The Artifact prompt")
    apply_default: bool = Field(
        False, description="Whether to apply this Artifact by default"
    )
    lifecycle_phase: Optional[str] = Field(
        None,
        description="Project lifecycle phase for default construction templates",
    )
    skill_ids: Optional[List[str]] = Field(
        None, description="Skill IDs to append when this artifact is used in chat"
    )
    collection_ids: Optional[List[str]] = Field(
        None, description="Collection IDs to append when this artifact is used in chat"
    )
    mcp_tool_ids: Optional[List[str]] = Field(
        None, description="MCP tool IDs to append when this artifact is used in chat"
    )
    html_template_id: Optional[str] = Field(
        None, description="HTML template to select when this artifact is used in chat"
    )


class ArtifactUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Artifact name")
    title: Optional[str] = Field(None, description="Display title for the Artifact")
    description: Optional[str] = Field(
        None, description="Description of what this Artifact does"
    )
    prompt: Optional[str] = Field(None, description="The Artifact prompt")
    apply_default: Optional[bool] = Field(
        None, description="Whether to apply this Artifact by default"
    )
    lifecycle_phase: Optional[str] = Field(
        None,
        description="Project lifecycle phase for default construction templates",
    )
    skill_ids: Optional[List[str]] = Field(
        None, description="Skill IDs to append when this artifact is used in chat"
    )
    collection_ids: Optional[List[str]] = Field(
        None, description="Collection IDs to append when this artifact is used in chat"
    )
    mcp_tool_ids: Optional[List[str]] = Field(
        None, description="MCP tool IDs to append when this artifact is used in chat"
    )
    html_template_id: Optional[str] = Field(
        None, description="HTML template to select when this artifact is used in chat"
    )


class ArtifactResponse(BaseModel):
    id: str
    name: str
    title: str
    description: str
    prompt: str
    apply_default: bool
    lifecycle_phase: Optional[str] = None
    skill_ids: List[str] = Field(default_factory=list)
    collection_ids: List[str] = Field(default_factory=list)
    mcp_tool_ids: List[str] = Field(default_factory=list)
    html_template_id: Optional[str] = None
    created: str
    updated: str


class ArtifactExecuteRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    artifact_id: str = Field(..., description="ID of the Artifact to execute")
    input_text: str = Field(..., description="Text to transform")
    model_id: str = Field(..., description="Model ID to use for the Artifact")


class ArtifactExecuteResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    output: str = Field(..., description="Transformed text")
    artifact_id: str = Field(..., description="ID of the Artifact used")
    model_id: str = Field(..., description="Model ID used")


# Canonical names for the global prompt library (table `artifact`, IDs `artifact:…`)
ArtifactTemplateCreate = ArtifactCreate
ArtifactTemplateUpdate = ArtifactUpdate
ArtifactTemplateResponse = ArtifactResponse
ArtifactTemplateExecuteRequest = ArtifactExecuteRequest
ArtifactTemplateExecuteResponse = ArtifactExecuteResponse


# Default Prompt API models
class DefaultPromptResponse(BaseModel):
    artifact_instructions: str = Field(..., description="Default Artifact instructions")


class DefaultPromptUpdate(BaseModel):
    artifact_instructions: str = Field(..., description="Default Artifact instructions")


# Project Artifacts API models (persisted project outputs; table `note`)
class ProjectArtifactCreate(BaseModel):
    title: Optional[str] = Field(None, description="Artifact title")
    content: str = Field(..., description="Artifact content")
    artifact_kind: Optional[str] = Field(
        None,
        description="Provenance kind: manual, ai, or generated",
    )
    note_type: Optional[str] = Field(
        None,
        description="Deprecated alias for artifact_kind (legacy values accepted)",
    )
    project_id: Optional[str] = Field(
        None, description="Project ID to add the artifact to"
    )


class ProjectArtifactUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Artifact title")
    content: Optional[str] = Field(None, description="Artifact content")
    artifact_kind: Optional[str] = Field(
        None, description="Provenance kind: manual, ai, or generated"
    )
    note_type: Optional[str] = Field(
        None, description="Deprecated alias for artifact_kind"
    )


class ProjectArtifactResponse(BaseModel):
    id: str
    title: Optional[str]
    content: Optional[str]
    artifact_kind: Optional[str]
    note_type: Optional[str] = Field(
        None, description="Deprecated alias mirroring artifact_kind"
    )
    created: str
    updated: str
    command_id: Optional[str] = None


# Legacy aliases
class NoteCreate(ProjectArtifactCreate):
    note_type: Optional[str] = Field(
        "manual",
        description="Deprecated — use artifact_kind (manual, ai, generated)",
    )


class NoteUpdate(ProjectArtifactUpdate):
    pass


class NoteResponse(ProjectArtifactResponse):
    pass


# Embedding API models
class EmbedRequest(BaseModel):
    item_id: str = Field(..., description="ID of the item to embed")
    item_type: str = Field(..., description="Type of item (source, note)")
    async_processing: bool = Field(
        False, description="Process asynchronously in background"
    )
    chain_kg: bool = Field(
        True,
        description=(
            "For sources: when True, continue into knowledge graph after embeddings. "
            "When False, only create embeddings."
        ),
    )


class EmbedResponse(BaseModel):
    success: bool = Field(..., description="Whether embedding was successful")
    message: str = Field(..., description="Result message")
    item_id: str = Field(..., description="ID of the item that was embedded")
    item_type: str = Field(..., description="Type of item that was embedded")
    command_id: Optional[str] = Field(
        None, description="Command ID for async processing"
    )


# Rebuild request/response models
class RebuildRequest(BaseModel):
    mode: Literal["existing", "all"] = Field(
        ...,
        description="Rebuild mode: 'existing' only re-embeds items with embeddings, 'all' embeds everything",
    )
    include_sources: bool = Field(True, description="Include sources in rebuild")
    include_artifacts: Optional[bool] = Field(
        None, description="Include project artifacts in rebuild (canonical)"
    )
    include_notes: bool = Field(
        True, description="Deprecated alias for include_artifacts"
    )
    chain_kg: bool = Field(
        False,
        description=(
            "When True, source rebuild jobs continue into knowledge-graph extraction. "
            "Default False refreshes embeddings only (faster, lower cost). "
            "Enable when graph nodes must match re-chunked embeddings."
        ),
    )

    def resolve_include_artifacts(self) -> bool:
        if self.include_artifacts is not None:
            return self.include_artifacts
        return self.include_notes


class RebuildResponse(BaseModel):
    command_id: str = Field(..., description="Command ID to track progress")
    total_items: int = Field(..., description="Estimated number of items to process")
    message: str = Field(..., description="Status message")


class RebuildProgress(BaseModel):
    processed: int = Field(..., description="Number of items processed")
    total: int = Field(..., description="Total items to process")
    percentage: float = Field(..., description="Progress percentage")


class RebuildStats(BaseModel):
    sources: int = Field(0, description="Sources processed")
    notes: int = Field(0, description="Notes processed")
    failed: int = Field(0, description="Failed items")


class RebuildStatusResponse(BaseModel):
    command_id: str = Field(..., description="Command ID")
    status: str = Field(..., description="Status: queued, running, completed, failed")
    progress: Optional[RebuildProgress] = None
    stats: Optional[RebuildStats] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


# Settings API models
class SettingsResponse(BaseModel):
    default_content_processing_engine_doc: Optional[str] = None
    default_content_processing_engine_url: Optional[str] = None
    default_embedding_option: Optional[str] = None
    auto_delete_files: Optional[str] = None
    youtube_preferred_languages: Optional[List[str]] = None


class SettingsUpdate(BaseModel):
    default_content_processing_engine_doc: Optional[str] = None
    default_content_processing_engine_url: Optional[str] = None
    default_embedding_option: Optional[str] = None
    auto_delete_files: Optional[str] = None
    youtube_preferred_languages: Optional[List[str]] = None


# Sources API models
class AssetModel(BaseModel):
    file_path: Optional[str] = None
    url: Optional[str] = None


class SourceCreate(BaseModel):
    # Backward compatibility: support old single project_id
    project_id: Optional[str] = Field(
        None, description="Project ID to add the source to (deprecated, use projects)"
    )
    # New multi-Project support
    projects: Optional[List[str]] = Field(
        None, description="List of Project IDs to add the source to"
    )
    # Required fields
    type: str = Field(..., description="Source type: link, upload, or text")
    url: Optional[str] = Field(None, description="URL for link type")
    file_path: Optional[str] = Field(None, description="File path for upload type")
    content: Optional[str] = Field(None, description="Text content for text type")
    title: Optional[str] = Field(None, description="Source title")
    artifacts: Optional[List[str]] = Field(
        default_factory=list, description="Artifact IDs to apply"
    )
    embed: bool = Field(False, description="Whether to embed content for vector search")
    delete_source: bool = Field(
        False, description="Whether to delete uploaded file after processing"
    )
    # New async processing support
    async_processing: bool = Field(
        False, description="Whether to process source asynchronously"
    )

    @model_validator(mode="after")
    def validate_project_fields(self):
        # Ensure only one of project_id or projects is provided
        if self.project_id is not None and self.projects is not None:
            raise ValueError(
                "Cannot specify both 'project_id' and 'projects'. Use 'projects' for multi-Project support."
            )

        # Convert single project_id to projects array for internal processing
        if self.project_id is not None:
            self.projects = [self.project_id]
            # Keep project_id for backward compatibility in response

        # Set empty array if no projects specified (allow sources without projects)
        if self.projects is None:
            self.projects = []

        return self


class SourceUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Source title")
    topics: Optional[List[str]] = Field(None, description="Source topics")


class ProcessingFailureResponse(BaseModel):
    stage: Literal["embedding", "knowledge_graph"]
    message: str
    error_type: Optional[str] = None
    occurred_at: Optional[datetime] = None
    command_id: Optional[str] = None


class SourceResponse(BaseModel):
    id: str
    title: Optional[str]
    topics: Optional[List[str]]
    asset: Optional[AssetModel]
    full_text: Optional[str]
    embedded: bool
    embedded_chunks: int
    file_available: Optional[bool] = None
    created: str
    updated: str
    # New fields for async processing
    command_id: Optional[str] = None
    status: Optional[str] = None
    processing_info: Optional[Dict] = None
    pipeline_stage: Optional[str] = None
    stage: Optional[str] = None
    processing_failures: Dict[str, ProcessingFailureResponse] = Field(
        default_factory=dict
    )
    failure_details_unavailable: bool = False
    # Project associations
    projects: Optional[List[str]] = None

    @field_validator("processing_failures", mode="before")
    @classmethod
    def normalize_processing_failures(cls, value: Any) -> Dict[str, Any]:
        """Treat absent/non-mapping ORM attributes as no recorded failures."""
        return value if isinstance(value, dict) else {}


class SourceListResponse(BaseModel):
    id: str
    title: Optional[str]
    topics: Optional[List[str]]
    asset: Optional[AssetModel]
    embedded: bool  # Boolean flag indicating if source has embeddings
    embedded_chunks: int  # Number of embedded chunks
    created: str
    updated: str
    file_available: Optional[bool] = None
    # Status fields for async processing
    command_id: Optional[str] = None
    status: Optional[str] = None
    processing_info: Optional[Dict[str, Any]] = None
    pipeline_stage: Optional[str] = None
    stage: Optional[str] = None
    # Child-job status for per-stage UI (from FETCH'd kg_command)
    kg_status: Optional[str] = None
    # Durable completion flag (like embedded) — true when a completed KG run exists
    knowledge_graph: bool = False
    # Latest architectural drawing extraction run status (independent of source pipeline)
    drawing_status: Optional[str] = None
    processing_failures: Dict[str, ProcessingFailureResponse] = Field(
        default_factory=dict
    )
    failure_details_unavailable: bool = False


# Context API models
class ContextConfig(BaseModel):
    sources: Dict[str, str] = Field(
        default_factory=dict, description="Source inclusion config {source_id: level}"
    )
    artifacts: Dict[str, str] = Field(
        default_factory=dict,
        description="Project artifact inclusion config {artifact_id: level}",
    )
    notes: Dict[str, str] = Field(
        default_factory=dict,
        description="Deprecated alias for artifacts {note_id: level}",
    )

    def resolved_artifacts(self) -> Dict[str, str]:
        """Merge legacy notes with canonical artifacts (artifacts win on conflict)."""
        return {**self.notes, **self.artifacts}


class ContextRequest(BaseModel):
    project_id: str = Field(..., description="Project ID to get context for")
    context_config: Optional[ContextConfig] = Field(
        None, description="Context configuration"
    )


class ContextResponse(BaseModel):
    project_id: str
    sources: List[Dict[str, Any]] = Field(..., description="Source context data")
    notes: List[Dict[str, Any]] = Field(..., description="Note context data")
    total_tokens: Optional[int] = Field(None, description="Estimated token count")



class SaveAsNoteRequest(BaseModel):
    project_id: Optional[str] = Field(None, description="Project ID to add note to")


class IngestTextSourceRequest(BaseModel):
    content: str = Field(..., description="Text content to ingest")
    title: str = Field(..., description="Source title")
    project_ids: List[str] = Field(
        ..., description="Project IDs to link the new source to"
    )
    embed: bool = Field(True, description="Whether to embed content for vector search")
    artifacts: Optional[List[str]] = Field(
        default_factory=list, description="Artifact IDs to apply after ingestion"
    )


class PromoteToSourceRequest(BaseModel):
    project_id: Optional[str] = Field(
        None,
        description="Project ID to link the source to (optional if already linked)",
    )
    embed: bool = Field(True, description="Whether to embed content for vector search")
    artifacts: Optional[List[str]] = Field(
        default_factory=list, description="Artifact IDs to apply after ingestion"
    )



class SourceStatusResponse(BaseModel):
    status: Optional[str] = Field(None, description="Processing status")
    message: str = Field(..., description="Descriptive message about the status")
    processing_info: Optional[Dict[str, Any]] = Field(
        None, description="Detailed processing information"
    )
    command_id: Optional[str] = Field(None, description="Command ID if available")
    stage: Optional[str] = Field(
        None,
        description="Pipeline stage: extracting|embedding|knowledge_graph|completed|failed",
    )
    embedded: Optional[bool] = Field(
        None, description="Whether the source currently has vector embeddings"
    )
    kg_status: Optional[str] = Field(
        None, description="Knowledge graph job status when linked"
    )
    knowledge_graph: Optional[bool] = Field(
        None,
        description="Whether a completed knowledge-graph extraction exists",
    )
    processing_failures: Dict[str, ProcessingFailureResponse] = Field(
        default_factory=dict
    )
    failure_details_unavailable: bool = False


# Error response
class ErrorResponse(BaseModel):
    error: str
    message: str


# API Key Configuration models
class SetApiKeyRequest(BaseModel):
    """Request to set an API key for a provider."""

    api_key: Optional[str] = Field(None, description="API key for the provider")
    base_url: Optional[str] = Field(
        None, description="Base URL for URL-based providers (Ollama, OpenAI-compatible)"
    )
    endpoint: Optional[str] = Field(None, description="Endpoint URL for Azure OpenAI")
    api_version: Optional[str] = Field(None, description="API version for Azure OpenAI")
    endpoint_llm: Optional[str] = Field(
        None, description="Service-specific endpoint for LLM (Azure)"
    )
    endpoint_embedding: Optional[str] = Field(
        None, description="Service-specific endpoint for embedding (Azure)"
    )
    endpoint_stt: Optional[str] = Field(
        None, description="Service-specific endpoint for STT (Azure)"
    )
    endpoint_tts: Optional[str] = Field(
        None, description="Service-specific endpoint for TTS (Azure)"
    )
    service_type: Optional[Literal["llm", "embedding", "stt", "tts"]] = Field(
        None,
        description="Service type for OpenAI-compatible providers (llm, embedding, stt, tts)",
    )
    # Vertex AI specific fields
    vertex_project: Optional[str] = Field(
        None, description="Google Cloud Project ID for Vertex AI"
    )
    vertex_location: Optional[str] = Field(
        None, description="Google Cloud Region for Vertex AI (e.g., us-central1)"
    )
    vertex_credentials_path: Optional[str] = Field(
        None, description="Path to Google Cloud service account JSON file"
    )

    @field_validator(
        "api_key",
        "base_url",
        "endpoint",
        "api_version",
        "endpoint_llm",
        "endpoint_embedding",
        "endpoint_stt",
        "endpoint_tts",
        "vertex_project",
        "vertex_location",
        "vertex_credentials_path",
        mode="before",
    )
    @classmethod
    def validate_not_empty_string(cls, v: Optional[str]) -> Optional[str]:
        """Reject empty strings - convert to None or raise error."""
        if v is not None:
            stripped = v.strip()
            if not stripped:
                return None  # Treat empty/whitespace-only as None
            return stripped
        return v


class ApiKeyStatusResponse(BaseModel):
    """Response showing which providers are configured and their source."""

    configured: Dict[str, bool] = Field(
        ..., description="Map of provider name to whether it is configured"
    )
    source: Dict[str, Literal["database", "environment", "none"]] = Field(
        ...,
        description="Map of provider name to configuration source (database, environment, or none)",
    )
    encryption_configured: bool = Field(
        ...,
        description="Whether CONSTRUCTION_OS_ENCRYPTION_KEY is set (required to store keys in database)",
    )


class TestConnectionResponse(BaseModel):
    """Response from testing a provider connection."""

    provider: str = Field(..., description="Provider name that was tested")
    success: bool = Field(..., description="Whether connection test succeeded")
    message: str = Field(..., description="Result message with details")


class MigrateFromEnvRequest(BaseModel):
    """Request to migrate API keys from environment variables to database."""

    force: bool = Field(
        False, description="Force overwrite existing database configurations"
    )


class MigrationResult(BaseModel):
    """Response from migrating API keys from environment to database."""

    message: str = Field(..., description="Summary message")
    migrated: List[str] = Field(
        default_factory=list, description="Providers successfully migrated"
    )
    skipped: List[str] = Field(
        default_factory=list, description="Providers skipped (already in DB)"
    )
    errors: List[str] = Field(
        default_factory=list, description="Migration errors by provider"
    )


# Project delete cascade models
# Credential models
class CreateCredentialRequest(BaseModel):
    """Request to create a new credential."""

    name: str = Field(..., description="Credential name")
    provider: str = Field(..., description="Provider name (openai, anthropic, etc.)")
    modalities: List[str] = Field(
        default_factory=list,
        description="Supported modalities (language, embedding, text_to_speech, speech_to_text)",
    )
    api_key: Optional[str] = Field(None, description="API key (stored encrypted)")
    base_url: Optional[str] = Field(None, description="Base URL")
    endpoint: Optional[str] = Field(None, description="Endpoint URL (Azure)")
    api_version: Optional[str] = Field(None, description="API version (Azure)")
    endpoint_llm: Optional[str] = Field(None, description="LLM endpoint")
    endpoint_embedding: Optional[str] = Field(None, description="Embedding endpoint")
    endpoint_stt: Optional[str] = Field(None, description="STT endpoint")
    endpoint_tts: Optional[str] = Field(None, description="TTS endpoint")
    project: Optional[str] = Field(None, description="Project ID (Vertex)")
    location: Optional[str] = Field(None, description="Location (Vertex)")
    credentials_path: Optional[str] = Field(
        None, description="Credentials file path (Vertex)"
    )
    num_ctx: Optional[int] = Field(
        None, description="Context window size (Ollama only; defaults to 8192)"
    )


class UpdateCredentialRequest(BaseModel):
    """Request to update an existing credential."""

    name: Optional[str] = Field(None, description="Credential name")
    modalities: Optional[List[str]] = Field(None, description="Supported modalities")
    api_key: Optional[str] = Field(None, description="API key (stored encrypted)")
    base_url: Optional[str] = Field(None, description="Base URL")
    endpoint: Optional[str] = Field(None, description="Endpoint URL")
    api_version: Optional[str] = Field(None, description="API version")
    endpoint_llm: Optional[str] = Field(None, description="LLM endpoint")
    endpoint_embedding: Optional[str] = Field(None, description="Embedding endpoint")
    endpoint_stt: Optional[str] = Field(None, description="STT endpoint")
    endpoint_tts: Optional[str] = Field(None, description="TTS endpoint")
    project: Optional[str] = Field(None, description="Project ID")
    location: Optional[str] = Field(None, description="Location")
    credentials_path: Optional[str] = Field(None, description="Credentials path")
    num_ctx: Optional[int] = Field(
        None, description="Context window size (Ollama only; defaults to 8192)"
    )


class CredentialResponse(BaseModel):
    """Response for a credential (never includes api_key)."""

    id: str
    name: str
    provider: str
    modalities: List[str]
    base_url: Optional[str] = None
    endpoint: Optional[str] = None
    api_version: Optional[str] = None
    endpoint_llm: Optional[str] = None
    endpoint_embedding: Optional[str] = None
    endpoint_stt: Optional[str] = None
    endpoint_tts: Optional[str] = None
    project: Optional[str] = None
    location: Optional[str] = None
    credentials_path: Optional[str] = None
    num_ctx: Optional[int] = None
    has_api_key: bool = False
    created: str
    updated: str
    model_count: int = 0
    decryption_error: Optional[str] = None


class CredentialDeleteResponse(BaseModel):
    """Response for credential deletion."""

    message: str
    deleted_models: int = 0


class DiscoveredModelResponse(BaseModel):
    """A model discovered from a provider."""

    name: str
    provider: str
    model_type: Optional[str] = None
    description: Optional[str] = None


class DiscoverModelsResponse(BaseModel):
    """Response from model discovery."""

    credential_id: str
    provider: str
    discovered: List[DiscoveredModelResponse]


class RegisterModelData(BaseModel):
    """A model to register with user-specified type."""

    name: str
    provider: str
    model_type: str  # Required: user specifies the type


class RegisterModelsRequest(BaseModel):
    """Request to register discovered models."""

    models: List[RegisterModelData]


class RegisterModelsResponse(BaseModel):
    """Response from model registration."""

    created: int
    existing: int


class ProjectDeletePreview(BaseModel):
    project_id: str = Field(..., description="ID of the Project")
    project_name: str = Field(..., description="Name of the Project")
    note_count: int = Field(..., description="Number of notes that will be deleted")
    exclusive_source_count: int = Field(
        ..., description="Number of sources only in this Project"
    )
    shared_source_count: int = Field(
        ..., description="Number of sources shared with other projects"
    )


class ProjectDeleteResponse(BaseModel):
    message: str = Field(..., description="Success message")
    deleted_notes: int = Field(..., description="Number of notes deleted")
    deleted_sources: int = Field(..., description="Number of exclusive sources deleted")
    unlinked_sources: int = Field(
        ..., description="Number of sources unlinked from Project"
    )


# --- HTML-native bid documents ---


class HtmlTemplateCreate(BaseModel):
    name: str = Field(..., description="Template display name")
    category: str = Field("estimate", description="estimate | sow | rfi | other")
    html_body: str = Field(..., description="Full HTML template body")


class HtmlTemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    html_body: Optional[str] = None


class HtmlTemplateResponse(BaseModel):
    id: str
    name: str
    category: str
    html_body: str
    created: str
    updated: str


class DocumentCreate(BaseModel):
    template_id: str = Field(..., description="HtmlTemplate id to copy from")
    title: Optional[str] = Field(
        None, description="Document title; defaults to template name"
    )
    scenario_label: str = Field("Base", description="Scenario label")
    html_body: Optional[str] = Field(
        None,
        description="Optional filled HTML; when set, used instead of copying template body",
    )


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    scenario_label: Optional[str] = None
    html_body: Optional[str] = None
    span_updates: Optional[Dict[int, str]] = Field(
        None, description="Page/Amounts span index → text replacements"
    )
    allow_structure_change: bool = Field(
        False,
        description="True when Code view saves full HTML (may change span structure)",
    )


class DocumentDuplicateRequest(BaseModel):
    scenario_label: str = Field(..., description="Label for the new scenario copy")
    title: Optional[str] = None


class DocumentPdfRenderRequest(BaseModel):
    html_body: str = Field(..., description="Full HTML document to render as PDF")
    title: Optional[str] = Field(None, description="Used for the download filename")


class DocumentResponse(BaseModel):
    id: str
    project_id: str
    template_id: Optional[str] = None
    title: str
    scenario_label: str
    html_body: str
    parent_document_id: Optional[str] = None
    created: str
    updated: str


# --- Global media asset library ---


class MediaAssetUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None


class MediaAssetResponse(BaseModel):
    id: str
    name: str
    slug: str
    mime_type: str
    byte_size: int
    created: str
    updated: str
    file_url: str = Field(..., description="Authenticated API path to fetch the file")


# --- Persistent per-session chat queue ---

ChatQueueStatus = Literal["active", "paused"]
ChatQueueRunnerState = Literal["idle", "scheduled", "running"]
ChatQueueItemStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
ChatQueueItemRunnerState = Literal[
    "idle", "scheduled", "running", "completed", "failed"
]


class ChatQueueExecutionSnapshot(BaseModel):
    """Immutable model and selector inputs captured when an item is enqueued."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    model_id: Optional[str] = None
    skill_ids: Optional[List[str]] = Field(default_factory=list)
    collection_ids: Optional[List[str]] = Field(default_factory=list)
    tool_ids: Optional[List[str]] = Field(default_factory=list)
    html_template_id: Optional[str] = None
    artifact_id: Optional[str] = None
    context_config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    forwarded_props: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ChatQueueItemEnqueueRequest(BaseModel):
    """Request to idempotently enqueue a persistent chat prompt."""

    model_config = ConfigDict(protected_namespaces=())

    client_request_id: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=100_000)
    loop_count: int = Field(default=1, ge=1, le=10)
    model_id: Optional[str] = None
    skill_ids: Optional[List[str]] = None
    collection_ids: Optional[List[str]] = None
    tool_ids: List[str] = Field(default_factory=list)
    html_template_id: Optional[str] = None
    artifact_id: Optional[str] = None
    context_config: Dict[str, Any] = Field(default_factory=dict)
    forwarded_props: Dict[str, Any] = Field(default_factory=dict)
    # When False, persist the item but do not schedule drain_chat_queue yet.
    # Use while a live AG-UI turn is in progress for the same session, then
    # call GET queue / resume to start the runner after that turn ends.
    schedule_runner: bool = True

    @field_validator("client_request_id", "prompt", mode="before")
    @classmethod
    def trim_required_text(cls, value: Any) -> Any:
        """Trim stable request IDs and prompts before length validation."""
        return value.strip() if isinstance(value, str) else value

    def to_execution_snapshot(
        self,
        *,
        default_model_id: Optional[str] = None,
        default_skill_ids: Optional[List[str]] = None,
        default_collection_ids: Optional[List[str]] = None,
        default_html_template_id: Optional[str] = None,
    ) -> ChatQueueExecutionSnapshot:
        """Resolve omitted session selectors into one immutable execution snapshot."""
        supplied = self.model_fields_set
        model_id = self.model_id if "model_id" in supplied else default_model_id
        skill_ids = (
            list(self.skill_ids or [])
            if "skill_ids" in supplied
            else list(default_skill_ids or [])
        )
        collection_ids = (
            list(self.collection_ids or [])
            if "collection_ids" in supplied
            else list(default_collection_ids or [])
        )
        html_template_id = (
            self.html_template_id
            if "html_template_id" in supplied
            else default_html_template_id
        )
        return ChatQueueExecutionSnapshot(
            model_id=model_id,
            skill_ids=skill_ids,
            collection_ids=collection_ids,
            tool_ids=self.tool_ids,
            html_template_id=html_template_id,
            artifact_id=self.artifact_id,
            context_config=self.context_config,
            forwarded_props=self.forwarded_props,
        )


class ChatQueueItemUpdateRequest(BaseModel):
    """Mutable fields accepted while an item is pending or failed."""

    model_config = ConfigDict(protected_namespaces=())

    prompt: Optional[str] = Field(default=None, min_length=1, max_length=100_000)
    loop_count: Optional[int] = Field(default=None, ge=1, le=10)
    model_id: Optional[str] = None
    skill_ids: Optional[List[str]] = None
    collection_ids: Optional[List[str]] = None
    tool_ids: Optional[List[str]] = None
    html_template_id: Optional[str] = None
    artifact_id: Optional[str] = None
    context_config: Optional[Dict[str, Any]] = None
    forwarded_props: Optional[Dict[str, Any]] = None

    @field_validator("prompt", mode="before")
    @classmethod
    def trim_optional_prompt(cls, value: Any) -> Any:
        """Trim prompt updates before non-empty and length validation."""
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_update(self) -> "ChatQueueItemUpdateRequest":
        """Require at least one explicitly supplied update field."""
        if not self.model_fields_set:
            raise ValueError("At least one queue item field must be provided")
        for field_name in ("prompt", "loop_count"):
            if (
                field_name in self.model_fields_set
                and getattr(self, field_name) is None
            ):
                raise ValueError(f"{field_name} cannot be null")
        return self

    def selector_patch(self) -> Dict[str, Any]:
        """Return only selector fields explicitly supplied by the caller."""
        selector_fields = {
            "model_id",
            "skill_ids",
            "collection_ids",
            "tool_ids",
            "html_template_id",
            "artifact_id",
            "context_config",
            "forwarded_props",
        }
        return {
            field_name: getattr(self, field_name)
            for field_name in self.model_fields_set
            if field_name in selector_fields
        }


class ChatQueueStateUpdateRequest(BaseModel):
    """Request to pause or resume one session queue."""

    status: ChatQueueStatus


class ChatQueueReorderRequest(BaseModel):
    """Optimistic exact-set reorder request for all pending items."""

    item_ids: List[str]
    expected_revision: int = Field(ge=0)

    @field_validator("item_ids")
    @classmethod
    def reject_duplicate_item_ids(cls, value: List[str]) -> List[str]:
        """Reject duplicate IDs before attempting an exact-set reorder."""
        if len(value) != len(set(value)):
            raise ValueError("item_ids cannot contain duplicates")
        return value


class ChatQueueItemResponse(BaseModel):
    """Persisted queue item, including reconnectable execution state."""

    model_config = ConfigDict(protected_namespaces=())

    id: str
    queue_id: str
    chat_session: str
    client_request_id: str
    run_id: str
    position: int
    status: ChatQueueItemStatus
    visible: bool
    prompt: str
    loop_count: int
    current_loop: int
    iteration_token: Optional[str] = None
    execution_snapshot: ChatQueueExecutionSnapshot
    runner_command_id: Optional[str] = None
    runner_state: ChatQueueItemRunnerState
    stream_revision: int
    stream_content: str
    stream_progress: Optional[Dict[str, Any]] = None
    stream_activity: Optional[Dict[str, Any]] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    created: datetime
    updated: datetime


class ChatQueueResponse(BaseModel):
    """Queue state and its ordered visible items."""

    model_config = ConfigDict(protected_namespaces=())

    id: str
    chat_session: str
    status: ChatQueueStatus
    revision: int
    runner_state: ChatQueueRunnerState
    runner_command_id: Optional[str] = None
    lease_owner: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    items: List[ChatQueueItemResponse] = Field(default_factory=list)
    current_item: Optional[ChatQueueItemResponse] = None
    created: datetime
    updated: datetime


class ChatQueueStreamResponse(BaseModel):
    """Revisioned queue snapshot used to hydrate reconnecting SSE clients."""

    event: Literal["snapshot", "item", "queue", "heartbeat"]
    revision: int = Field(ge=0)
    queue: Optional[ChatQueueResponse] = None
    item: Optional[ChatQueueItemResponse] = None
