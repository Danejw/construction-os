import type { SourceListResponse } from '@/lib/types/api'

export type SourceKind = 'link' | 'upload' | 'text'

/** Stage completeness filter for embedding / knowledge graph / drawing. */
export type StageFilter = 'any' | 'complete' | 'incomplete'

export type SourceListFilterState = {
  query: string
  /** Coarse source kind. */
  kind: 'all' | SourceKind
  /** Lowercase extension without dot; empty = any. Only meaningful for uploads. */
  extension: string
  embedding: StageFilter
  knowledgeGraph: StageFilter
  drawing: StageFilter
}

export const DEFAULT_SOURCE_LIST_FILTERS: SourceListFilterState = {
  query: '',
  kind: 'all',
  extension: '',
  embedding: 'any',
  knowledgeGraph: 'any',
  drawing: 'any',
}

const DRAWING_DONE = new Set(['completed', 'partial'])
const DRAWING_RUNNING = new Set([
  'queued',
  'inspecting',
  'extracting',
  'validating',
  'publishing',
])

export function getSourceKind(source: SourceListResponse): SourceKind {
  if (source.asset?.url) return 'link'
  if (source.asset?.file_path) return 'upload'
  return 'text'
}

/** File extension from uploaded path, lowercase without leading dot. */
export function getSourceExtension(source: SourceListResponse): string | null {
  const path = source.asset?.file_path
  if (!path) return null
  const base = path.split(/[/\\]/).pop() || path
  const dot = base.lastIndexOf('.')
  if (dot <= 0 || dot === base.length - 1) return null
  return base.slice(dot + 1).toLowerCase()
}

export function isEmbeddingComplete(source: SourceListResponse): boolean {
  return Boolean(source.embedded)
}

export function isKnowledgeGraphComplete(source: SourceListResponse): boolean {
  return Boolean(source.knowledge_graph) || source.kg_status === 'completed'
}

export function isDrawingComplete(
  drawingStatus: string | null | undefined
): boolean {
  if (!drawingStatus) return false
  return DRAWING_DONE.has(drawingStatus)
}

export function isDrawingInProgress(
  drawingStatus: string | null | undefined
): boolean {
  if (!drawingStatus) return false
  return DRAWING_RUNNING.has(drawingStatus)
}

function matchesStage(filter: StageFilter, complete: boolean): boolean {
  if (filter === 'any') return true
  if (filter === 'complete') return complete
  return !complete
}

export function isSourceListFilterActive(filters: SourceListFilterState): boolean {
  return (
    filters.query.trim() !== '' ||
    filters.kind !== 'all' ||
    filters.extension !== '' ||
    filters.embedding !== 'any' ||
    filters.knowledgeGraph !== 'any' ||
    filters.drawing !== 'any'
  )
}

export function matchesSourceFilters(
  source: SourceListResponse,
  filters: SourceListFilterState,
  options?: { drawingStatus?: string | null }
): boolean {
  const query = filters.query.trim().toLowerCase()
  if (query) {
    const title = (source.title || '').toLowerCase()
    const url = (source.asset?.url || '').toLowerCase()
    const path = (source.asset?.file_path || '').toLowerCase()
    if (!title.includes(query) && !url.includes(query) && !path.includes(query)) {
      return false
    }
  }

  const kind = getSourceKind(source)
  if (filters.kind !== 'all' && kind !== filters.kind) {
    return false
  }

  if (filters.extension) {
    if (kind !== 'upload') return false
    const ext = getSourceExtension(source)
    if (ext !== filters.extension) return false
  }

  if (!matchesStage(filters.embedding, isEmbeddingComplete(source))) {
    return false
  }
  if (!matchesStage(filters.knowledgeGraph, isKnowledgeGraphComplete(source))) {
    return false
  }

  const drawingStatus =
    options?.drawingStatus !== undefined
      ? options.drawingStatus
      : source.drawing_status
  if (!matchesStage(filters.drawing, isDrawingComplete(drawingStatus))) {
    return false
  }

  return true
}

/** Unique extensions present among upload sources, sorted. */
export function collectSourceExtensions(
  sources: SourceListResponse[]
): string[] {
  const set = new Set<string>()
  for (const source of sources) {
    if (getSourceKind(source) !== 'upload') continue
    const ext = getSourceExtension(source)
    if (ext) set.add(ext)
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b))
}
