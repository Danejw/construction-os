export interface ProjectResponse {
  id: string
  name: string
  description: string
  archived: boolean
  created: string
  updated: string
  source_count: number
  note_count: number
}

export interface ProjectArtifactResponse {
  id: string
  title: string | null
  content: string | null
  artifact_kind: string | null
  note_type: string | null
  created: string
  updated: string
}

/** @deprecated Use ProjectArtifactResponse */
export type NoteResponse = ProjectArtifactResponse

export interface SourceProcessingFailure {
  stage: 'embedding' | 'knowledge_graph'
  message: string
  error_type?: string | null
  occurred_at?: string | null
  command_id?: string | null
}

export type SourceProcessingFailures = Partial<
  Record<SourceProcessingFailure['stage'], SourceProcessingFailure>
>

export interface SourceListResponse {
  id: string
  title: string | null
  topics?: string[]                  // Make optional to match Python API
  asset: {
    file_path?: string
    url?: string
  } | null
  embedded: boolean
  embedded_chunks: number            // ADD: From Python API
  created: string
  updated: string
  file_available?: boolean
  // ADD: Async processing fields from Python API
  command_id?: string
  status?: string
  processing_info?: Record<string, unknown>
  pipeline_stage?: string
  stage?: string
  kg_status?: string | null
  /** Durable flag — true when a completed KG extraction exists (like `embedded`). */
  knowledge_graph?: boolean
  drawing_status?: string | null
  processing_failures?: SourceProcessingFailures
  failure_details_unavailable?: boolean
}

export interface SourceDetailResponse extends SourceListResponse {
  full_text: string
  projects?: string[]
}

export type SourceResponse = SourceDetailResponse

export interface IngestTextSourceRequest {
  content: string
  title: string
  project_ids: string[]
  embed?: boolean
  artifacts?: string[]
}

export interface PromoteToSourceRequest {
  project_id?: string
  embed?: boolean
  artifacts?: string[]
}

export interface SourceStatusResponse {
  status?: string
  message: string
  processing_info?: Record<string, unknown>
  command_id?: string
  stage?: string
  embedded?: boolean | null
  kg_status?: string | null
  knowledge_graph?: boolean | null
  processing_failures?: SourceProcessingFailures
  failure_details_unavailable?: boolean
}

export interface SettingsResponse {
  default_content_processing_engine_doc?: string
  default_content_processing_engine_url?: string
  default_embedding_option?: string
  auto_delete_files?: string
  youtube_preferred_languages?: string[]
}

export interface CreateProjectRequest {
  name: string
  description?: string
}

export interface UpdateProjectRequest {
  name?: string
  description?: string
  archived?: boolean
}

export interface ProjectDeletePreview {
  project_id: string
  project_name: string
  note_count: number
  exclusive_source_count: number
  shared_source_count: number
}

export interface ProjectDeleteResponse {
  message: string
  deleted_notes: number
  deleted_sources: number
  unlinked_sources: number
}

export interface CreateProjectArtifactRequest {
  title?: string
  content: string
  artifact_kind?: string
  note_type?: string
  project_id?: string
}

/** @deprecated Use CreateProjectArtifactRequest */
export type CreateNoteRequest = CreateProjectArtifactRequest

export interface CreateSourceRequest {
  // Single-project convenience field.
  project_id?: string
  // Multi-project associations.
  projects?: string[]
  // Required fields
  type: 'link' | 'upload' | 'text'
  url?: string
  file_path?: string
  content?: string
  title?: string
  artifacts?: string[]
  embed?: boolean
  delete_source?: boolean
  // New async processing support
  async_processing?: boolean
}

export interface UpdateProjectArtifactRequest {
  title?: string
  content?: string
  artifact_kind?: string
  note_type?: string
}

/** @deprecated Use UpdateProjectArtifactRequest */
export type UpdateNoteRequest = UpdateProjectArtifactRequest

export interface UpdateSourceRequest {
  title?: string
  type?: 'link' | 'upload' | 'text'
  url?: string
  content?: string
}

export interface APIError {
  detail: string
}

// Source Chat Types
// Base session interface with common fields
export interface BaseChatSession {
  id: string
  title: string
  created: string
  updated: string
  message_count?: number
  model_override?: string | null
  skill_ids?: string[] | null
  collection_ids?: string[] | null
  html_template_id?: string | null
  guest_key?: string | null
}

/** Shared chat message shape used by project Chat UI. */
export interface ChatMessage {
  id: string
  type: 'human' | 'ai'
  content: string
  timestamp?: string
}

export interface ChatContextIndicator {
  sources: string[]
  notes: string[]
}

export interface SendMessageRequest {
  message: string
  model_override?: string
  skill_ids?: string[]
  collection_ids?: string[]
  mcp_tool_ids?: string[]
  html_template_id?: string | null
}

// Project Chat Types
export interface ProjectChatSession extends BaseChatSession {
  project_id: string
}

export interface ProjectChatMessage {
  id: string
  type: 'human' | 'ai'
  content: string
  timestamp?: string
  /** Optional A2UI v0.9 message array persisted with the AI message. */
  a2ui_payload?: Array<Record<string, unknown>> | null
}

export interface ProjectChatSessionWithMessages extends ProjectChatSession {
  messages: ProjectChatMessage[]
}

export interface CreateProjectChatSessionRequest {
  project_id: string
  title?: string
  model_override?: string
  skill_ids?: string[]
  collection_ids?: string[]
  html_template_id?: string | null
  guest_key?: string
}

export interface UpdateProjectChatSessionRequest {
  title?: string
  model_override?: string | null
  skill_ids?: string[]
  collection_ids?: string[]
  html_template_id?: string | null
}

export interface SendProjectChatMessageRequest {
  session_id: string
  message: string
  /** @deprecated Prefer context_config so retrieval streams as an AG-UI step */
  context?: {
    sources: Array<Record<string, unknown>>
    notes: Array<Record<string, unknown>>
  }
  context_config?: {
    sources: Record<string, string>
    artifacts?: Record<string, string>
    /** @deprecated Prefer artifacts */
    notes: Record<string, string>
  }
  model_override?: string
  skill_ids?: string[]
  collection_ids?: string[]
  mcp_tool_ids?: string[]
  html_template_id?: string | null
  edit_message_id?: string
  artifact_id?: string
}

export interface BuildContextRequest {
  project_id: string
  context_config: {
    sources: Record<string, string>
    artifacts?: Record<string, string>
    /** @deprecated Prefer artifacts */
    notes: Record<string, string>
  }
}

export interface BuildContextResponse {
  context: {
    sources: Array<Record<string, unknown>>
    notes: Array<Record<string, unknown>>
  }
  token_count: number
  char_count: number
}

export interface ChatSuggestionsRequest {
  scope: 'project' | 'source'
  project_id?: string
  source_id?: string
  count?: number
}

export interface ChatSuggestionsResponse {
  suggestions: string[]
}
