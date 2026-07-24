import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from '@tanstack/react-query'
import { useCallback, useMemo } from 'react'
import { sourcesApi } from '@/lib/api/sources'
import { projectsApi } from '@/lib/api/projects'
import { embeddingApi } from '@/lib/api/embedding'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useKnowledgeExtractStore } from '@/lib/stores/knowledge-extract-store'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import {
  buildOptimisticSource,
  prependSourceToAllQueries,
  replaceSourceInAllQueries,
  restoreSourceListQueries,
  snapshotSourceListQueries,
  removeSourceFromAllQueries,
  removeSourceFromProjectQueries,
  dedupeSourcesById,
  patchAllSourceListQueries,
} from '@/lib/utils/source-query-cache'
import {
  CreateSourceRequest,
  UpdateSourceRequest,
  SourceResponse,
  SourceStatusResponse,
  SourceListResponse,
  IngestTextSourceRequest,
  PromoteToSourceRequest,
} from '@/lib/types/api'

const PROJECT_SOURCES_PAGE_SIZE = 30

export function useSources(projectId?: string) {
  return useQuery({
    queryKey: QUERY_KEYS.sources(projectId),
    queryFn: () => sourcesApi.list({ project_id: projectId }),
    enabled: !!projectId,
    staleTime: 5 * 1000, // 5 seconds - more responsive for real-time source updates
    refetchOnWindowFocus: true, // Refetch when user comes back to the tab
  })
}

/**
 * Hook for fetching project sources with infinite scroll pagination.
 * Returns flattened sources array and pagination controls.
 */
export function useProjectSources(projectId: string) {
  const queryClient = useQueryClient()

  const query = useInfiniteQuery({
    queryKey: QUERY_KEYS.sourcesInfinite(projectId),
    queryFn: async ({ pageParam = 0 }) => {
      const data = await sourcesApi.list({
        project_id: projectId,
        limit: PROJECT_SOURCES_PAGE_SIZE,
        offset: pageParam,
        sort_by: 'updated',
        sort_order: 'desc',
      })
      return {
        sources: data,
        nextOffset: data.length === PROJECT_SOURCES_PAGE_SIZE ? pageParam + data.length : undefined,
      }
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) => lastPage.nextOffset,
    enabled: !!projectId,
    staleTime: 30 * 1000,
    refetchOnWindowFocus: false,
  })

  // Flatten pages; dedupe guards against pagination overlap + cache races
  const sources: SourceListResponse[] = useMemo(
    () => dedupeSourcesById(query.data?.pages.flatMap((page) => page.sources) ?? []),
    [query.data?.pages]
  )

  // Refetch function that resets to first page
  const refetch = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.sourcesInfinite(projectId) })
  }, [queryClient, projectId])

  return {
    sources,
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: query.hasNextPage,
    fetchNextPage: query.fetchNextPage,
    refetch,
    error: query.error,
  }
}

const ALL_SOURCES_PAGE_SIZE = 30

export type SourcesSortBy = 'created' | 'updated'
export type SourcesSortOrder = 'asc' | 'desc'

/**
 * Infinite list of all sources (global sources page).
 */
export function useAllSourcesInfinite(sortBy: SourcesSortBy, sortOrder: SourcesSortOrder) {
  const query = useInfiniteQuery({
    queryKey: QUERY_KEYS.sourcesAllInfinite(sortBy, sortOrder),
    queryFn: async ({ pageParam = 0 }) => {
      const data = await sourcesApi.list({
        limit: ALL_SOURCES_PAGE_SIZE,
        offset: pageParam,
        sort_by: sortBy,
        sort_order: sortOrder,
      })
      return {
        sources: data,
        nextOffset: data.length === ALL_SOURCES_PAGE_SIZE ? pageParam + data.length : undefined,
      }
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) => lastPage.nextOffset,
    staleTime: 30 * 1000,
    refetchOnWindowFocus: false,
    placeholderData: (previousData) => previousData,
  })

  const sources: SourceListResponse[] = useMemo(
    () => dedupeSourcesById(query.data?.pages.flatMap((page) => page.sources) ?? []),
    [query.data?.pages]
  )

  return {
    sources,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: query.hasNextPage,
    fetchNextPage: query.fetchNextPage,
    error: query.error,
    refetch: query.refetch,
  }
}

export function useSource(id: string) {
  return useQuery({
    queryKey: QUERY_KEYS.source(id),
    queryFn: () => sourcesApi.get(id),
    enabled: !!id,
    staleTime: 30 * 1000, // 30 seconds - shorter stale time for more responsive updates
    refetchOnWindowFocus: true, // Refetch when user comes back to the tab
  })
}

export function useUpdateSource() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string
      data: UpdateSourceRequest
    }) => sourcesApi.update(id, data),
    onSuccess: (result, { id }) => {
      queryClient.setQueryData(QUERY_KEYS.source(id), result)
      patchAllSourceListQueries(queryClient, (sources) =>
        sources.map((source) =>
          source.id === id ? { ...source, ...result } : source
        )
      )
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.source(id) })
      void queryClient.invalidateQueries({ queryKey: ['sources'] })
      toast({
        title: t('common.success'),
        description: t('sources.sourceUpdatedSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(
          error,
          (key) => t(key),
          t('sources.failedToUpdateSource')
        ),
        variant: 'destructive',
      })
    },
  })
}

export function useCreateSource() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: CreateSourceRequest & { file?: File }) =>
      sourcesApi.create(data),
    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: ['sources'] })
      const previous = snapshotSourceListQueries(queryClient)
      const optimistic = buildOptimisticSource(variables)
      prependSourceToAllQueries(queryClient, optimistic)
      return { previous, optimisticId: optimistic.id }
    },
    onSuccess: (result: SourceResponse, variables, context) => {
      if (context?.optimisticId) {
        replaceSourceInAllQueries(queryClient, context.optimisticId, result)
      }
      // Keep KG status polling active while auto-extract runs after upload
      useKnowledgeExtractStore.getState().markPending(result.id)

      // Invalidate queries for all relevant projects with immediate refetch
      if (variables.projects) {
        variables.projects.forEach(projectId => {
          queryClient.invalidateQueries({
            queryKey: QUERY_KEYS.sources(projectId),
            refetchType: 'active'
          })
          queryClient.invalidateQueries({
            queryKey: QUERY_KEYS.sourcesInfinite(projectId),
            refetchType: 'active'
          })
        })
      } else if (variables.project_id) {
        queryClient.invalidateQueries({
          queryKey: QUERY_KEYS.sources(variables.project_id),
          refetchType: 'active'
        })
        queryClient.invalidateQueries({
          queryKey: QUERY_KEYS.sourcesInfinite(variables.project_id),
          refetchType: 'active'
        })
      }

      // Invalidate general sources query too with immediate refetch
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.sources(),
        refetchType: 'active'
      })

      // Show different messages based on processing mode
      if (variables.async_processing) {
        toast({
          title: t('sources.sourceQueued'),
          description: t('sources.sourceQueuedPipelineDesc'),
        })
      } else {
        toast({
          title: t('common.success'),
          description: t('sources.sourceAddedSuccess'),
        })
      }
    },
    onError: (error: unknown, _variables, context) => {
      if (context?.previous) {
        restoreSourceListQueries(queryClient, context.previous)
      }
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.failedToAddSource')),
        variant: 'destructive',
      })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['sources'] })
    },
  })
}

export function useDeleteSource() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (id: string) => sourcesApi.delete(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['sources'] })
      const previous = snapshotSourceListQueries(queryClient)
      removeSourceFromAllQueries(queryClient, id)
      return { previous }
    },
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.source(id) })
      toast({
        title: t('common.success'),
        description: t('sources.sourceDeletedSuccess'),
      })
    },
    onError: (error: unknown, _id, context) => {
      if (context?.previous) {
        restoreSourceListQueries(queryClient, context.previous)
      }
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.failedToDeleteSource')),
        variant: 'destructive',
      })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['sources'] })
    },
  })
}

export function useSourceStatus(sourceId: string, enabled = true) {
  return useQuery({
    queryKey: ['sources', sourceId, 'status'],
    queryFn: () => sourcesApi.status(sourceId),
    enabled: !!sourceId && enabled,
    refetchInterval: (query) => {
      // Auto-refresh every 2 seconds while the full pipeline is in progress
      // (extract → embed → knowledge graph), including after overall status
      // flips to completed while the KG child job / durable flag is settling.
      // Embeddings stay green because `embedded` is true before stage exits;
      // keep polling until `knowledge_graph` is true once a KG job finished.
      const data = query.state.data as SourceStatusResponse | undefined
      const stage = data?.stage
      const kgStatus = data?.kg_status
      const awaitingKgDurable =
        data?.knowledge_graph !== true &&
        (stage === 'knowledge_graph' ||
          kgStatus === 'running' ||
          kgStatus === 'queued' ||
          kgStatus === 'new')
      if (
        data?.status === 'running' ||
        data?.status === 'queued' ||
        data?.status === 'new' ||
        stage === 'extracting' ||
        stage === 'embedding' ||
        stage === 'knowledge_graph' ||
        kgStatus === 'running' ||
        kgStatus === 'queued' ||
        kgStatus === 'new' ||
        awaitingKgDurable
      ) {
        return 2000
      }
      return false
    },
    staleTime: 0, // Always consider status data stale for real-time updates
    retry: (failureCount, error) => {
      // Don't retry on 404 (source not found)
      const axiosError = error as { response?: { status?: number } }
      if (axiosError?.response?.status === 404) {
        return false
      }
      return failureCount < 3
    },
  })
}

export function useRetrySource() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (sourceId: string) => sourcesApi.retry(sourceId),
    onSuccess: (result, sourceId) => {
      // Invalidate status query to refetch latest status
      queryClient.invalidateQueries({
        queryKey: ['sources', sourceId, 'status']
      })
      // Invalidate ALL sources queries to refresh the UI
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.source(sourceId) })

      toast({
        title: t('sources.sourceRequeued'),
        description: t('sources.sourceRequeuedDesc'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.failedToRetry')),
        variant: 'destructive',
      })
    },
  })
}

export function useBulkRetrySources() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: async (sourceIds: string[]) => {
      const results = await Promise.allSettled(
        sourceIds.map((sourceId) => sourcesApi.retry(sourceId))
      )
      const successes = results.filter((r) => r.status === 'fulfilled').length
      const failures = results.length - successes
      return { successes, failures, total: sourceIds.length, sourceIds }
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      for (const sourceId of result.sourceIds) {
        queryClient.invalidateQueries({
          queryKey: ['sources', sourceId, 'status'],
        })
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.source(sourceId) })
      }

      if (result.successes > 0) {
        toast({
          title: t('sources.bulkRetryQueued').replace(
            '{count}',
            String(result.successes)
          ),
          description: t('sources.sourceRequeuedDesc'),
        })
      }
      if (result.failures > 0) {
        toast({
          title: t('common.error'),
          description: t('sources.bulkRetryPartial').replace(
            '{failed}',
            String(result.failures)
          ),
          variant: 'destructive',
        })
      }
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.failedToRetry')),
        variant: 'destructive',
      })
    },
  })
}

export function useEmbedSource() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({
      sourceId,
      chainKg = false,
    }: {
      sourceId: string
      chainKg?: boolean
    }) =>
      embeddingApi.embedContent(sourceId, 'source', {
        chainKg,
      }),
    onSuccess: (_result, { sourceId }) => {
      // Patch the one card in-place instead of refetching the whole project list
      // (large lists freeze the UI while every page reloads).
      patchAllSourceListQueries(queryClient, (sources) =>
        sources.map((source) =>
          source.id === sourceId
            ? {
                ...source,
                status: 'running',
                stage: 'embedding',
                pipeline_stage: 'embedding',
              }
            : source
        )
      )
      queryClient.setQueryData<SourceStatusResponse>(
        ['sources', sourceId, 'status'],
        (prev) => ({
          status: 'running',
          message: prev?.message || 'Creating vector embeddings…',
          processing_info: prev?.processing_info,
          command_id: prev?.command_id,
          stage: 'embedding',
          embedded: prev?.embedded ?? false,
          kg_status: prev?.kg_status ?? null,
          knowledge_graph: prev?.knowledge_graph ?? false,
          processing_failures: prev?.processing_failures,
          failure_details_unavailable: prev?.failure_details_unavailable,
        })
      )
      void queryClient.invalidateQueries({
        queryKey: ['sources', sourceId, 'status'],
      })
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.source(sourceId) })
      toast({
        title: t('sources.embeddingsQueued'),
        description: t('sources.embeddingsQueuedDesc'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(
          error,
          (key) => t(key),
          t('sources.embeddingsFailed')
        ),
        variant: 'destructive',
      })
    },
  })
}

export function useAddSourcesToProject() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: async ({ projectId, sourceIds }: { projectId: string; sourceIds: string[] }) => {
      // Use Promise.allSettled to handle partial failures gracefully
      const results = await Promise.allSettled(
        sourceIds.map(sourceId => projectsApi.addSource(projectId, sourceId))
      )

      // Count successes and failures
      const successes = results.filter(r => r.status === 'fulfilled').length
      const failures = results.filter(r => r.status === 'rejected').length

      return { successes, failures, total: sourceIds.length }
    },
    onSuccess: (result, { projectId, sourceIds }) => {
      // Invalidate ALL sources queries to refresh all lists
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      // Specifically invalidate the project's sources
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.sources(projectId) })
      // Invalidate each affected source
      sourceIds.forEach(sourceId => {
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.source(sourceId) })
      })

      // Show appropriate toast based on results
      if (result.failures === 0) {
        toast({
          title: t('common.success'),
          description: t('sources.sourcesAddedToProject').replace('{count}', result.successes.toString()),
        })
      } else if (result.successes === 0) {
        toast({
          title: t('common.error'),
          description: t('sources.failedToAddSourcesToProject'),
          variant: 'destructive',
        })
      } else {
        toast({
          title: t('common.success'),
          description: t('sources.partialAddSuccess')
            .replace('{success}', result.successes.toString())
            .replace('{failed}', result.failures.toString()),
          variant: 'default',
        })
      }
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.failedToAddSourcesToProject')),
        variant: 'destructive',
      })
    },
  })
}

export function useRemoveSourceFromProject() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: async ({ projectId, sourceId }: { projectId: string; sourceId: string }) => {
      return projectsApi.removeSource(projectId, sourceId)
    },
    onMutate: async ({ projectId, sourceId }) => {
      await queryClient.cancelQueries({ queryKey: ['sources'] })
      const previous = snapshotSourceListQueries(queryClient)
      removeSourceFromProjectQueries(queryClient, projectId, sourceId)
      return { previous }
    },
    onSuccess: (_, { projectId, sourceId }) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.source(sourceId) })
      toast({
        title: t('common.success'),
        description: t('sources.sourceRemovedFromProject'),
      })
    },
    onError: (error: unknown, _vars, context) => {
      if (context?.previous) {
        restoreSourceListQueries(queryClient, context.previous)
      }
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.failedToRemoveSourceFromProject')),
        variant: 'destructive',
      })
    },
    onSettled: (_data, _error, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.sources(projectId) })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.sourcesInfinite(projectId) })
    },
  })
}

type IngestAsSourceInput =
  | { kind: 'text'; data: IngestTextSourceRequest; projectId?: string }
  | { kind: 'note'; noteId: string; projectId?: string; options?: PromoteToSourceRequest }

export function useIngestAsSource() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: async (input: IngestAsSourceInput) => {
      if (input.kind === 'text') {
        return sourcesApi.ingestText(input.data)
      }
      if (input.kind === 'note') {
        return sourcesApi.ingestNoteAsSource(input.noteId, {
          project_id: input.projectId ?? input.options?.project_id,
          embed: input.options?.embed,
          artifacts: input.options?.artifacts,
        })
      }
      throw new Error('Unsupported ingest kind')
    },
    onSuccess: (_result, input) => {
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      const projectId =
        input.kind === 'text'
          ? input.data.project_ids[0]
          : input.projectId ?? input.options?.project_id
      if (projectId) {
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.sources(projectId) })
      }
      toast({
        title: t('common.success'),
        description: t('sources.ingestSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.ingestFailed')),
        variant: 'destructive',
      })
    },
  })
}
