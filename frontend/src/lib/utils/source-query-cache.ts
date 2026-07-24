import type { InfiniteData, QueryClient, QueryKey } from '@tanstack/react-query'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { SourceListResponse } from '@/lib/types/api'

type SourcesInfinitePage = {
  sources: SourceListResponse[]
  nextOffset?: number
}

type SourcesInfiniteData = InfiniteData<SourcesInfinitePage>

function isSourcesInfiniteData(data: unknown): data is SourcesInfiniteData {
  return (
    typeof data === 'object' &&
    data !== null &&
    'pages' in data &&
    Array.isArray((data as SourcesInfiniteData).pages)
  )
}

/** Update every sources list cache (flat arrays and infinite-query pages). */
export function patchAllSourceListQueries(
  queryClient: QueryClient,
  patchPage: (sources: SourceListResponse[]) => SourceListResponse[]
) {
  const entries = queryClient.getQueriesData<unknown>({ queryKey: ['sources'] })

  for (const [queryKey, data] of entries) {
    if (isSourcesInfiniteData(data)) {
      queryClient.setQueryData<SourcesInfiniteData>(queryKey, {
        ...data,
        pages: data.pages.map((page) => ({
          ...page,
          sources: patchPage(page.sources),
        })),
      })
      continue
    }

    if (Array.isArray(data)) {
      queryClient.setQueryData<SourceListResponse[]>(
        queryKey,
        patchPage(data as SourceListResponse[])
      )
    }
  }
}

/** Keep first occurrence of each source id (page order preserved). */
export function dedupeSourcesById(sources: SourceListResponse[]): SourceListResponse[] {
  const seen = new Set<string>()
  return sources.filter((source) => {
    if (seen.has(source.id)) return false
    seen.add(source.id)
    return true
  })
}

export function removeSourceFromAllQueries(queryClient: QueryClient, sourceId: string) {
  patchAllSourceListQueries(queryClient, (sources) =>
    sources.filter((source) => source.id !== sourceId)
  )
}

/**
 * Prepend a source to list caches.
 * For infinite queries, only touch the first page and strip the id from later
 * pages — applying the same prepend to every page creates duplicate React keys.
 */
export function prependSourceToAllQueries(
  queryClient: QueryClient,
  source: SourceListResponse
) {
  const entries = queryClient.getQueriesData<unknown>({ queryKey: ['sources'] })

  for (const [queryKey, data] of entries) {
    if (isSourcesInfiniteData(data)) {
      queryClient.setQueryData<SourcesInfiniteData>(queryKey, {
        ...data,
        pages: data.pages.map((page, index) => {
          const without = page.sources.filter((item) => item.id !== source.id)
          if (index === 0) {
            return { ...page, sources: [source, ...without] }
          }
          return { ...page, sources: without }
        }),
      })
      continue
    }

    if (Array.isArray(data)) {
      const list = data as SourceListResponse[]
      queryClient.setQueryData<SourceListResponse[]>(queryKey, [
        source,
        ...list.filter((item) => item.id !== source.id),
      ])
    }
  }
}

export function replaceSourceInAllQueries(
  queryClient: QueryClient,
  sourceId: string,
  replacement: SourceListResponse
) {
  const entries = queryClient.getQueriesData<unknown>({ queryKey: ['sources'] })

  for (const [queryKey, data] of entries) {
    if (isSourcesInfiniteData(data)) {
      let replaced = false
      queryClient.setQueryData<SourcesInfiniteData>(queryKey, {
        ...data,
        pages: data.pages.map((page, index) => {
          const next = page.sources.flatMap((source) => {
            if (source.id === sourceId || source.id === replacement.id) {
              if (replaced) return []
              replaced = true
              return [replacement]
            }
            return [source]
          })
          // If optimistic id was missing (race), put replacement on first page
          if (index === 0 && !replaced) {
            replaced = true
            return { ...page, sources: [replacement, ...next] }
          }
          return { ...page, sources: next }
        }),
      })
      continue
    }

    if (Array.isArray(data)) {
      const list = data as SourceListResponse[]
      let replaced = false
      const next = list.flatMap((source) => {
        if (source.id === sourceId || source.id === replacement.id) {
          if (replaced) return []
          replaced = true
          return [replacement]
        }
        return [source]
      })
      queryClient.setQueryData<SourceListResponse[]>(
        queryKey,
        replaced ? next : [replacement, ...next]
      )
    }
  }
}

export function removeSourceFromProjectQueries(
  queryClient: QueryClient,
  projectId: string,
  sourceId: string
) {
  queryClient.setQueryData<SourceListResponse[]>(QUERY_KEYS.sources(projectId), (old) =>
    old?.filter((source) => source.id !== sourceId)
  )

  queryClient.setQueryData<SourcesInfiniteData>(QUERY_KEYS.sourcesInfinite(projectId), (old) => {
    if (!old?.pages) return old
    return {
      ...old,
      pages: old.pages.map((page) => ({
        ...page,
        sources: page.sources.filter((source) => source.id !== sourceId),
      })),
    }
  })
}

export function snapshotSourceListQueries(queryClient: QueryClient) {
  return queryClient.getQueriesData<unknown>({ queryKey: ['sources'] }) as [
    QueryKey,
    unknown,
  ][]
}

export function restoreSourceListQueries(
  queryClient: QueryClient,
  snapshots: [QueryKey, unknown][]
) {
  for (const [queryKey, data] of snapshots) {
    queryClient.setQueryData(queryKey, data)
  }
}

export function buildOptimisticSource(
  variables: {
    title?: string
    type: 'link' | 'upload' | 'text'
    url?: string
    file_path?: string
    file?: File
    async_processing?: boolean
  },
  id = `optimistic-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
): SourceListResponse {
  const now = new Date().toISOString()
  const fileName =
    variables.file instanceof File ? variables.file.name : undefined
  const uploadPath = variables.file_path ?? fileName

  return {
    id,
    title: variables.title ?? fileName ?? null,
    asset:
      variables.type === 'link' && variables.url
        ? { url: variables.url }
        : variables.type === 'upload' && uploadPath
          ? { file_path: uploadPath }
          : null,
    embedded: false,
    embedded_chunks: 0,
    knowledge_graph: false,
    created: now,
    updated: now,
    status: variables.async_processing ? 'queued' : undefined,
    stage: variables.async_processing ? 'queued' : undefined,
    pipeline_stage: variables.async_processing ? 'queued' : undefined,
  }
}
