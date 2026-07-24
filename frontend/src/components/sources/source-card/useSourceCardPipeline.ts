'use client'

import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { SourceListResponse, SourceStatusResponse } from '@/lib/types/api'
import { patchAllSourceListQueries } from '@/lib/utils/source-query-cache'
import { useSourceStatus, useEmbedSource } from '@/lib/hooks/use-sources'
import {
  useExtractKnowledge,
  useSourceExtractors,
} from '@/lib/hooks/use-knowledge'
import { useGraphLiveStore } from '@/lib/stores/graph-live-store'
import { useKnowledgeExtractStore } from '@/lib/stores/knowledge-extract-store'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { StageActionState } from '@/components/sources/SourceStageActions'
import {
  type SourceCardListFields,
  type SourceStatus,
  drawingProgressLabelKey,
  drawingStageState,
  getStatusConfig,
  isSourceStatus,
  resolveDrawingFillPercent,
  resolvePipelineFillPercent,
} from '@/components/sources/source-card/sourceCardStatus'

export interface UseSourceCardPipelineArgs {
  source: SourceListResponse
  projectId?: string
  menuOpen: boolean
  drawingStatus?: string | null
  drawingBusy?: boolean
}

function isKgJobActive(kgStatus: string | null | undefined): boolean {
  return (
    kgStatus === 'new' || kgStatus === 'queued' || kgStatus === 'running'
  )
}

/**
 * Durable KG completion — same idea as `embedded`: true once evidence exists.
 * Prefer any true signal; never let a stale status `false` block a true list flag.
 */
function resolveLiveKnowledgeGraph(
  statusData: SourceStatusResponse | undefined,
  source: SourceCardListFields,
  extractorKgStatus: string | undefined
): boolean {
  return (
    statusData?.knowledge_graph === true ||
    source.knowledge_graph === true ||
    statusData?.kg_status === 'completed' ||
    source.kg_status === 'completed' ||
    extractorKgStatus === 'completed'
  )
}

export function useSourceCardPipeline({
  source,
  projectId,
  menuOpen,
  drawingStatus,
  drawingBusy = false,
}: UseSourceCardPipelineArgs) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [wasProcessing, setWasProcessing] = useState(false)
  const [sawKnowledgeGraphStage, setSawKnowledgeGraphStage] = useState(false)
  const wasKnowledgeGraphRef = useRef(false)

  const sourceWithStatus = source as SourceCardListFields

  const listStage = sourceWithStatus.stage || sourceWithStatus.pipeline_stage
  const listKgStatus = sourceWithStatus.kg_status ?? null
  const listKnowledgeGraph = Boolean(sourceWithStatus.knowledge_graph)

  // Keep fetching until durable KG lands after we observed the KG stage
  // (embeddings already exist before that stage exits; KG can lag one poll).
  const awaitingKgDurable =
    sawKnowledgeGraphStage &&
    !listKnowledgeGraph &&
    listKgStatus !== 'failed' &&
    listKgStatus !== 'completed'

  const shouldFetchStatus =
    sourceWithStatus.status === 'new' ||
    sourceWithStatus.status === 'queued' ||
    sourceWithStatus.status === 'running' ||
    listStage === 'extracting' ||
    listStage === 'embedding' ||
    listStage === 'knowledge_graph' ||
    isKgJobActive(listKgStatus) ||
    (!!sourceWithStatus.command_id && !sourceWithStatus.status) ||
    wasProcessing ||
    awaitingKgDurable

  const { data: statusData, isLoading: statusLoading } = useSourceStatus(
    source.id,
    shouldFetchStatus
  )

  const pipelineStage =
    statusData?.stage ||
    (typeof statusData?.processing_info?.stage === 'string'
      ? statusData.processing_info.stage
      : undefined) ||
    listStage

  const rawStatus = statusData?.status || sourceWithStatus.status
  const currentStatus: SourceStatus = isSourceStatus(rawStatus)
    ? rawStatus
    : sourceWithStatus.command_id
      ? 'new'
      : 'completed'

  const liveKgStatusFromPoll = statusData?.kg_status
  const kgStillActive = isKgJobActive(liveKgStatusFromPoll)

  useEffect(() => {
    const currentStatusFromData = statusData?.status || sourceWithStatus.status
    const stage =
      statusData?.stage ||
      sourceWithStatus.stage ||
      sourceWithStatus.pipeline_stage

    if (stage === 'knowledge_graph') {
      wasKnowledgeGraphRef.current = true
      setSawKnowledgeGraphStage(true)
      if (projectId) {
        useGraphLiveStore.getState().setSourceUpdating(projectId, source.id, true)
      }
    }

    if (
      currentStatusFromData === 'new' ||
      currentStatusFromData === 'running' ||
      currentStatusFromData === 'queued' ||
      stage === 'extracting' ||
      stage === 'embedding' ||
      stage === 'knowledge_graph' ||
      kgStillActive
    ) {
      setWasProcessing(true)
    }

    // Keep polling until durable KG matches embeddings' EXISTS check.
    if (kgStillActive) {
      return
    }
    if (
      wasKnowledgeGraphRef.current &&
      statusData?.knowledge_graph !== true &&
      sourceWithStatus.knowledge_graph !== true &&
      statusData?.kg_status !== 'completed' &&
      sourceWithStatus.kg_status !== 'completed' &&
      statusData?.kg_status !== 'failed'
    ) {
      return
    }

    if (
      wasProcessing &&
      (currentStatusFromData === 'completed' ||
        currentStatusFromData === 'failed') &&
      (stage === 'completed' || stage === 'failed' || !stage)
    ) {
      setWasProcessing(false)
      useKnowledgeExtractStore.getState().clearPending(source.id)

      if (projectId) {
        if (
          wasKnowledgeGraphRef.current &&
          currentStatusFromData === 'completed'
        ) {
          useGraphLiveStore
            .getState()
            .notifySourceKnowledgeReady(projectId, source.id)
        } else {
          useGraphLiveStore
            .getState()
            .setSourceUpdating(projectId, source.id, false)
        }
      }
      wasKnowledgeGraphRef.current = false
      setSawKnowledgeGraphStage(false)

      const nextKgStatus = statusData?.kg_status ?? sourceWithStatus.kg_status
      const nextKnowledgeGraph =
        statusData?.knowledge_graph === true ||
        sourceWithStatus.knowledge_graph === true ||
        nextKgStatus === 'completed'

      patchAllSourceListQueries(queryClient, (sources) =>
        sources.map((item) =>
          item.id === source.id
            ? {
                ...item,
                status: currentStatusFromData,
                stage: stage || currentStatusFromData,
                pipeline_stage: stage || item.pipeline_stage,
                embedded:
                  typeof statusData?.embedded === 'boolean'
                    ? statusData.embedded
                    : item.embedded,
                kg_status: nextKgStatus,
                knowledge_graph: nextKnowledgeGraph || item.knowledge_graph,
                processing_failures:
                  statusData?.processing_failures ?? item.processing_failures,
                failure_details_unavailable:
                  statusData?.failure_details_unavailable ??
                  item.failure_details_unavailable,
              }
            : item
        )
      )

      // Keep status cache in sync so a disabled query doesn't stick on false.
      queryClient.setQueryData(
        ['sources', source.id, 'status'],
        (prev: SourceStatusResponse | undefined) =>
          prev
            ? {
                ...prev,
                status: currentStatusFromData,
                stage: stage || prev.stage,
                embedded:
                  typeof statusData?.embedded === 'boolean'
                    ? statusData.embedded
                    : prev.embedded,
                kg_status: nextKgStatus ?? prev.kg_status,
                knowledge_graph:
                  nextKnowledgeGraph || prev.knowledge_graph === true,
              }
            : prev
      )

      void queryClient.invalidateQueries({ queryKey: ['sources'] })
    }
  }, [
    statusData,
    sourceWithStatus.status,
    sourceWithStatus.stage,
    sourceWithStatus.pipeline_stage,
    sourceWithStatus.kg_status,
    sourceWithStatus.knowledge_graph,
    wasProcessing,
    kgStillActive,
    source.id,
    projectId,
    queryClient,
  ])

  const statusConfigMap = getStatusConfig(t)
  const stageStatusKey =
    pipelineStage === 'extracting' ||
    pipelineStage === 'embedding' ||
    pipelineStage === 'knowledge_graph'
      ? pipelineStage
      : currentStatus
  const statusConfig =
    statusConfigMap[stageStatusKey as keyof typeof statusConfigMap] ||
    statusConfigMap.completed

  const isProcessing: boolean =
    currentStatus === 'new' ||
    currentStatus === 'running' ||
    currentStatus === 'queued' ||
    pipelineStage === 'extracting' ||
    pipelineStage === 'embedding' ||
    pipelineStage === 'knowledge_graph'
  const isFailed: boolean =
    currentStatus === 'failed' || pipelineStage === 'failed'
  const isCompleted: boolean = currentStatus === 'completed' && !isFailed
  const apiProgress =
    typeof statusData?.processing_info?.progress === 'number'
      ? Math.round(statusData.processing_info.progress as number)
      : null
  const statusLabel =
    isProcessing &&
    typeof statusData?.message === 'string' &&
    statusData.message.trim()
      ? statusData.message.replace(/\u2026$/, '').replace(/\.\.\.$/, '').trim() ||
        statusConfig.label
      : statusConfig.label

  const isKgPending = useKnowledgeExtractStore((state) =>
    Boolean(state.pendingSourceIds[source.id])
  )
  const { data: extractorData, isFetching: kgStatusLoading } =
    useSourceExtractors(source.id, isCompleted && (menuOpen || isKgPending))
  const extractKnowledge = useExtractKnowledge(source.id)
  const embedSource = useEmbedSource()
  const genericRun = extractorData?.extractors?.find((e) => e.id === 'generic')
  const extractorKgStatus = genericRun?.last_run?.status
  const processingFailures =
    statusData?.processing_failures ?? sourceWithStatus.processing_failures
  const embedFailure = processingFailures?.embedding
  const kgFailure =
    processingFailures?.knowledge_graph ??
    (genericRun?.last_run?.status === 'failed' &&
    genericRun.last_run.error_message
      ? {
          stage: 'knowledge_graph' as const,
          message: genericRun.last_run.error_message,
          occurred_at:
            genericRun.last_run.finished_at ?? genericRun.last_run.started_at,
          command_id: genericRun.last_run.command_id,
        }
      : undefined)
  const failureDetailsUnavailable =
    statusData?.failure_details_unavailable ??
    sourceWithStatus.failure_details_unavailable ??
    false

  // Embeddings: durable boolean from status poll (EXISTS) or list row.
  const liveEmbedded =
    typeof statusData?.embedded === 'boolean'
      ? statusData.embedded
      : Boolean(sourceWithStatus.embedded)

  // Knowledge graph: same durable-boolean idea (completed kg_extraction_run).
  const liveKnowledgeGraph = resolveLiveKnowledgeGraph(
    statusData,
    sourceWithStatus,
    extractorKgStatus
  )
  const liveKgStatus =
    statusData?.kg_status ??
    sourceWithStatus.kg_status ??
    extractorKgStatus ??
    null
  const kgFailed =
    liveKgStatus === 'failed' || extractorKgStatus === 'failed'
  const showBuildKnowledgeGraph =
    isCompleted &&
    menuOpen &&
    !kgStatusLoading &&
    !liveKnowledgeGraph &&
    !(
      extractKnowledge.isBuilding ||
      isKgJobActive(liveKgStatus)
    )

  const extractReady =
    liveEmbedded ||
    pipelineStage === 'embedding' ||
    pipelineStage === 'knowledge_graph' ||
    pipelineStage === 'completed' ||
    pipelineStage === 'failed' ||
    isCompleted ||
    isFailed

  const embedState: StageActionState =
    pipelineStage === 'embedding' || embedSource.isPending
      ? 'running'
      : embedFailure || (isFailed && !liveEmbedded)
        ? 'failed'
        : liveEmbedded
          ? 'done'
          : 'idle'

  // Mirror embedState exactly: running in-stage / building; done from durable flag.
  const kgState: StageActionState =
    pipelineStage === 'knowledge_graph' || extractKnowledge.isBuilding
      ? 'running'
      : kgFailure || (isFailed && liveEmbedded && !liveKnowledgeGraph)
        ? 'failed'
        : liveKnowledgeGraph
          ? 'done'
          : 'idle'

  const kgBuilding = kgState === 'running'
  const hasKnowledgeGraph = liveKnowledgeGraph
  const resolvedDrawingStatus =
    drawingStatus ?? sourceWithStatus.drawing_status ?? null
  const drawingState = drawingStageState(resolvedDrawingStatus)
  const isDrawingProcessing = drawingState === 'running' || Boolean(drawingBusy)
  const showProgressFill = isProcessing || isDrawingProcessing
  const fillPercent = isProcessing
    ? resolvePipelineFillPercent(pipelineStage, currentStatus, apiProgress)
    : isDrawingProcessing
      ? resolveDrawingFillPercent(resolvedDrawingStatus)
      : 0
  const progressLabel = isProcessing
    ? statusData?.message || statusLabel
    : isDrawingProcessing
      ? t(drawingProgressLabelKey(resolvedDrawingStatus))
      : statusLabel

  const handleBuildKnowledgeGraph = () => {
    extractKnowledge.mutate({
      extractor: 'generic',
      project_id: projectId,
      force: true,
    })
  }

  const handleRunEmbeddings = () => {
    embedSource.mutate({ sourceId: source.id, chainKg: false })
  }

  return {
    shouldFetchStatus,
    statusData,
    statusLoading,
    pipelineStage,
    statusConfig,
    statusLabel,
    isProcessing,
    isFailed,
    isCompleted,
    showProgressFill,
    fillPercent,
    progressLabel,
    extractReady,
    embedState,
    kgState,
    drawingState,
    resolvedDrawingStatus,
    embedFailure,
    kgFailure,
    failureDetailsUnavailable,
    kgStatusLoading,
    kgBuilding,
    kgFailed,
    showBuildKnowledgeGraph,
    hasKnowledgeGraph,
    extractKnowledge,
    embedSource,
    handleBuildKnowledgeGraph,
    handleRunEmbeddings,
  }
}
