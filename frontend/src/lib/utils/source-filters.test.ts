import { describe, expect, it } from 'vitest'
import type { SourceListResponse } from '@/lib/types/api'
import {
  collectSourceExtensions,
  DEFAULT_SOURCE_LIST_FILTERS,
  getSourceExtension,
  getSourceKind,
  isDrawingComplete,
  isEmbeddingComplete,
  isKnowledgeGraphComplete,
  isSourceListFilterActive,
  matchesSourceFilters,
} from '@/lib/utils/source-filters'

function source(
  overrides: Partial<SourceListResponse> & Pick<SourceListResponse, 'id'>
): SourceListResponse {
  return {
    title: 'Untitled',
    topics: [],
    asset: null,
    embedded: false,
    embedded_chunks: 0,
    created: '2026-01-01T00:00:00Z',
    updated: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('source-filters', () => {
  it('detects source kind and extension', () => {
    expect(
      getSourceKind(source({ id: '1', asset: { url: 'https://x.test' } }))
    ).toBe('link')
    expect(
      getSourceKind(
        source({ id: '2', asset: { file_path: 'notes/Page_A701.pdf' } })
      )
    ).toBe('upload')
    expect(getSourceKind(source({ id: '3' }))).toBe('text')
    expect(
      getSourceExtension(
        source({ id: '4', asset: { file_path: 'notes/Page_A701.PDF' } })
      )
    ).toBe('pdf')
  })

  it('matches name and process completeness filters', () => {
    const pdf = source({
      id: 'pdf',
      title: 'Ceiling Specs',
      asset: { file_path: 'a701.pdf' },
      embedded: true,
      kg_status: null,
      drawing_status: 'completed',
    })

    expect(
      matchesSourceFilters(pdf, {
        ...DEFAULT_SOURCE_LIST_FILTERS,
        query: 'ceiling',
      })
    ).toBe(true)

    expect(
      matchesSourceFilters(pdf, {
        ...DEFAULT_SOURCE_LIST_FILTERS,
        extension: 'pdf',
      })
    ).toBe(true)

    expect(isEmbeddingComplete(pdf)).toBe(true)
    expect(isKnowledgeGraphComplete(pdf)).toBe(false)
    expect(
      isKnowledgeGraphComplete({ ...pdf, knowledge_graph: true })
    ).toBe(true)
    expect(isDrawingComplete(pdf.drawing_status)).toBe(true)

    expect(
      matchesSourceFilters(pdf, {
        ...DEFAULT_SOURCE_LIST_FILTERS,
        knowledgeGraph: 'incomplete',
        drawing: 'complete',
      })
    ).toBe(true)

    expect(
      matchesSourceFilters(pdf, {
        ...DEFAULT_SOURCE_LIST_FILTERS,
        embedding: 'incomplete',
      })
    ).toBe(false)
  })

  it('collects unique extensions and reports active filters', () => {
    const list = [
      source({ id: '1', asset: { file_path: 'a.pdf' } }),
      source({ id: '2', asset: { file_path: 'b.MD' } }),
      source({ id: '3', asset: { url: 'https://x.test' } }),
    ]
    expect(collectSourceExtensions(list)).toEqual(['md', 'pdf'])
    expect(isSourceListFilterActive(DEFAULT_SOURCE_LIST_FILTERS)).toBe(false)
    expect(
      isSourceListFilterActive({
        ...DEFAULT_SOURCE_LIST_FILTERS,
        drawing: 'complete',
      })
    ).toBe(true)
  })
})
