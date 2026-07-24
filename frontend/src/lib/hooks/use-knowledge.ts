import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { knowledgeApi } from '@/lib/api/knowledge'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useGraphLiveStore } from '@/lib/stores/graph-live-store'
import { useKnowledgeExtractStore } from '@/lib/stores/knowledge-extract-store'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import { patchAllSourceListQueries } from '@/lib/utils/source-query-cache'

export const KNOWLEDGE_QUERY_KEYS = {
  extractors: (sourceId: string) => ['knowledge', 'extractors', sourceId] as const,
  source: (sourceId: string) => ['knowledge', 'source', sourceId] as const,
}

function patchSourceKgStatus(
  queryClient: ReturnType<typeof useQueryClient>,
  sourceId: string,
  kgStatus: string
) {
  const knowledgeGraph = kgStatus === 'completed'
  patchAllSourceListQueries(queryClient, (sources) =>
    sources.map((source) =>
      source.id === sourceId
        ? {
            ...source,
            kg_status: kgStatus,
            // Durable flag — same role as `embedded` for the list icon.
            ...(knowledgeGraph ? { knowledge_graph: true } : {}),
          }
        : source
    )
  )
  queryClient.setQueryData(
    ['sources', sourceId, 'status'],
    (prev: { knowledge_graph?: boolean | null; kg_status?: string | null } | undefined) =>
      prev
        ? {
            ...prev,
            kg_status: kgStatus,
            ...(knowledgeGraph ? { knowledge_graph: true } : {}),
          }
        : prev
  )
  void queryClient.invalidateQueries({
    queryKey: ['sources', sourceId, 'status'],
  })
  void queryClient.invalidateQueries({ queryKey: ['sources'] })
}

function invalidateSourceKnowledge(
  queryClient: ReturnType<typeof useQueryClient>,
  sourceId: string,
  projectId?: string
) {
  queryClient.invalidateQueries({
    queryKey: KNOWLEDGE_QUERY_KEYS.extractors(sourceId),
  })
  queryClient.invalidateQueries({
    queryKey: KNOWLEDGE_QUERY_KEYS.source(sourceId),
  })
  if (projectId) {
    queryClient.invalidateQueries({
      queryKey: ['knowledge', 'project', projectId],
    })
    queryClient.invalidateQueries({
      queryKey: ['knowledge-graph', 'overview', projectId],
    })
  }
}

function markExtractorRunning(
  queryClient: ReturnType<typeof useQueryClient>,
  sourceId: string,
  extractor: string,
  commandId: string
) {
  queryClient.setQueryData(
    KNOWLEDGE_QUERY_KEYS.extractors(sourceId),
    (old: { extractors: Array<{ id: string; last_run?: Record<string, unknown> }> } | undefined) => {
      if (!old?.extractors) {
        return {
          extractors: [
            {
              id: extractor,
              label: extractor,
              version: '',
              auto_run: extractor === 'generic',
              last_run: { status: 'running', command_id: commandId },
            },
          ],
        }
      }
      return {
        ...old,
        extractors: old.extractors.map((item) =>
          item.id === extractor
            ? {
                ...item,
                last_run: {
                  ...(item.last_run ?? {}),
                  status: 'running',
                  command_id: commandId,
                  error_message: undefined,
                },
              }
            : item
        ),
      }
    }
  )
}

async function watchExtractCommand(options: {
  commandId: string
  sourceId: string
  projectId?: string
  t: (key: string) => string
  queryClient: ReturnType<typeof useQueryClient>
}) {
  const { commandId, sourceId, projectId, t, queryClient } = options
  const store = useKnowledgeExtractStore.getState()
  store.markPending(sourceId)
  if (projectId) {
    useGraphLiveStore.getState().setSourceUpdating(projectId, sourceId, true)
  }

  try {
    const status = await knowledgeApi.waitForCommand(commandId)
    await invalidateSourceKnowledge(queryClient, sourceId, projectId)

    if (status.status === 'completed') {
      patchSourceKgStatus(queryClient, sourceId, 'completed')
      if (projectId) {
        useGraphLiveStore
          .getState()
          .notifySourceKnowledgeReady(projectId, sourceId)
      }
      const stats = status.result?.stats as
        | Record<string, number | string | undefined>
        | undefined
      const entities = Number(stats?.entities ?? 0)
      const claims = Number(stats?.claims ?? 0)
      const relations = Number(stats?.relations ?? 0)
      const hasContent = entities + claims + relations > 0
      if (!hasContent && stats?.reason !== 'unchanged_content_hash') {
        toast.warning(t('knowledge.extractEmpty'), {
          description: t('knowledge.extractEmptyHint'),
        })
        return
      }
      if (entities > 0 && relations === 0) {
        toast.warning(t('knowledge.extractCompleted'), {
          description: t('knowledge.extractNoRelationsHint'),
        })
        return
      }
      toast.success(t('knowledge.extractCompleted'), {
        description: t('knowledge.statsSummary')
          .replace('{entities}', String(entities))
          .replace('{claims}', String(claims))
          .replace('{relations}', String(relations)),
      })
      return
    }

    if (status.status === 'failed') {
      patchSourceKgStatus(queryClient, sourceId, 'failed')
      toast.error(t('knowledge.extractRunFailed'), {
        description:
          status.error_message ||
          t('knowledge.extractRunFailedHint'),
      })
      return
    }

    toast.message(t('knowledge.extractWatchTimeout'))
  } catch (error) {
    toast.error(t('knowledge.extractRunFailed'), {
      description: getApiErrorMessage(error, t),
    })
    await invalidateSourceKnowledge(queryClient, sourceId, projectId)
  } finally {
    store.clearPending(sourceId)
    if (projectId) {
      useGraphLiveStore.getState().setSourceUpdating(projectId, sourceId, false)
    }
  }
}

export function useSourceExtractors(sourceId: string, enabled = true) {
  const isExtractPending = useKnowledgeExtractStore(
    (state) => Boolean(state.pendingSourceIds[sourceId])
  )

  return useQuery({
    queryKey: KNOWLEDGE_QUERY_KEYS.extractors(sourceId),
    queryFn: () => knowledgeApi.listExtractors(sourceId),
    enabled: !!sourceId && enabled,
    refetchInterval: (query) => {
      if (isExtractPending) return 2000
      const generic = query.state.data?.extractors?.find((e) => e.id === 'generic')
      const status = generic?.last_run?.status
      return status === 'running' || status === 'queued' ? 2000 : false
    },
  })
}

export function useSourceKnowledge(sourceId: string, enabled = true) {
  const isExtractPending = useKnowledgeExtractStore(
    (state) => Boolean(state.pendingSourceIds[sourceId])
  )

  return useQuery({
    queryKey: KNOWLEDGE_QUERY_KEYS.source(sourceId),
    queryFn: () => knowledgeApi.getSourceKnowledge(sourceId),
    enabled: !!sourceId && enabled,
    refetchInterval: isExtractPending ? 2000 : false,
  })
}

export function useExtractKnowledge(sourceId: string) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const isWatching = useKnowledgeExtractStore(
    (state) => Boolean(state.pendingSourceIds[sourceId])
  )

  const mutation = useMutation({
    mutationFn: (data: {
      extractor: string
      project_id?: string
      force?: boolean
    }) => knowledgeApi.extract(sourceId, data),
    onSuccess: (data, variables) => {
      toast.success(t('knowledge.extractQueued'), {
        description: t('knowledge.extractQueuedHint'),
      })
      markExtractorRunning(
        queryClient,
        sourceId,
        variables.extractor,
        data.command_id
      )
      void watchExtractCommand({
        commandId: data.command_id,
        sourceId,
        projectId: variables.project_id,
        t,
        queryClient,
      })
    },
    onError: (error: Error) => {
      toast.error(t('knowledge.extractFailed'), {
        description: getApiErrorMessage(error, t),
      })
    },
  })

  return {
    ...mutation,
    isWatching,
    isBuilding: mutation.isPending || isWatching,
  }
}

export function useBulkExtractKnowledge() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: {
      sourceIds: string[]
      project_id?: string
      extractor?: string
      force?: boolean
    }) => {
      const extractor = data.extractor ?? 'generic'
      const results = await Promise.allSettled(
        data.sourceIds.map((sourceId) =>
          knowledgeApi.extract(sourceId, {
            extractor,
            project_id: data.project_id,
            force: data.force ?? true,
          }).then((job) => ({ sourceId, ...job }))
        )
      )
      const queued = results.flatMap((r) =>
        r.status === 'fulfilled' ? [r.value] : []
      )
      const failed = results.length - queued.length
      return { queued, failed, total: results.length, project_id: data.project_id }
    },
    onSuccess: (result) => {
      toast.success(
        t('knowledge.bulkExtractQueued').replace(
          '{count}',
          String(result.queued.length)
        ),
        { description: t('knowledge.extractQueuedHint') }
      )
      if (result.failed > 0) {
        toast.error(
          t('knowledge.bulkExtractPartial').replace(
            '{failed}',
            String(result.failed)
          )
        )
      }

      for (const job of result.queued) {
        markExtractorRunning(
          queryClient,
          job.sourceId,
          job.extractor,
          job.command_id
        )
        void watchExtractCommand({
          commandId: job.command_id,
          sourceId: job.sourceId,
          projectId: result.project_id,
          t,
          queryClient,
        })
      }
    },
    onError: (error: Error) => {
      toast.error(t('knowledge.extractFailed'), {
        description: getApiErrorMessage(error, t),
      })
    },
  })
}
