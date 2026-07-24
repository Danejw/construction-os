'use client'

import React, { useState, memo } from 'react'
import type { SourceListResponse } from '@/lib/types/api'
import { useSelectableRow } from '@/lib/hooks/useSelectableRow'
import { useTranslation } from '@/lib/hooks/use-translation'
import { Checkbox } from '@/components/ui/checkbox'
import {
  getArtifactDragData,
  getActiveArtifactDragPayload,
  isArtifactDragEvent,
  clearArtifactDragData,
} from '@/lib/utils/artifact-drag'
import type { ContextMode } from '@/lib/types/project-context'
import { cn } from '@/lib/utils'
import { SourceStageActions } from '@/components/sources/SourceStageActions'
import { SourceCardActionMenu } from '@/components/sources/source-card/SourceCardActionMenu'
import { SourceCardStatusBadge } from '@/components/sources/source-card/SourceCardStatusBadge'
import { SourceCardChrome } from '@/components/sources/source-card/SourceCardChrome'
import { useSourceCardPipeline } from '@/components/sources/source-card/useSourceCardPipeline'
import {
  type SourceCardListFields,
  drawingProgressLabelKey,
  getSourceType,
  getSourceTypeLabel,
  topicsEqual,
} from '@/components/sources/source-card/sourceCardStatus'
import { getSourceDisplayIcon } from '@/lib/utils/source-icons'

export interface SourceCardProps {
  source: SourceListResponse
  projectId?: string
  onDelete?: (sourceId: string) => void
  onRetry?: (sourceId: string) => void
  onRefreshContent?: (sourceId: string) => void
  onRemoveFromProject?: (sourceId: string) => void
  onClick?: (sourceId: string) => void
  onRefresh?: () => void
  className?: string
  showRemoveFromProject?: boolean
  contextMode?: ContextMode
  onContextModeChange?: (mode: ContextMode) => void
  onArtifactDrop?: (artifactId: string) => void
  selectionMode?: boolean
  selected?: boolean
  onToggleSelect?: (sourceId: string) => void
  onEnterSelection?: (sourceId: string) => void
  /** Live drawing-run status from project polling (overrides list field). */
  drawingStatus?: string | null
  drawingRunId?: string | null
  onRunDrawingExtraction?: (sourceId: string) => void
  onInspectDrawing?: (runId: string) => void
  drawingBusy?: boolean
}

function SourceCardImpl({
  source,
  projectId,
  onClick,
  onDelete,
  onRetry,
  onRefreshContent,
  onRemoveFromProject,
  className,
  showRemoveFromProject = false,
  contextMode,
  onContextModeChange,
  onArtifactDrop,
  selectionMode = false,
  selected = false,
  onToggleSelect,
  onEnterSelection,
  drawingStatus,
  drawingRunId,
  onRunDrawingExtraction,
  onInspectDrawing,
  drawingBusy = false,
}: SourceCardProps) {
  const { t } = useTranslation()
  const [isArtifactDragOver, setIsArtifactDragOver] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  const pipeline = useSourceCardPipeline({
    source,
    projectId,
    menuOpen,
    drawingStatus,
    drawingBusy,
  })

  const sourceType = getSourceType(source)
  const { Icon: SourceTypeIcon, className: sourceIconClassName } =
    getSourceDisplayIcon(source)
  const sourceTypeLabel = getSourceTypeLabel(sourceType, t)
  const title = source.title || t('sources.untitledSource')
  const displayTitle = pipeline.showProgressFill
    ? pipeline.progressLabel
    : title
  const StatusIcon = pipeline.statusConfig.icon
  const drawingEligible = (source.asset?.file_path || '')
    .toLowerCase()
    .endsWith('.pdf')
  const showDrawingActions = Boolean(projectId && onRunDrawingExtraction)

  const { rowProps, selectedClassName } = useSelectableRow({
    selectionMode,
    selected,
    onToggleSelect: () => onToggleSelect?.(source.id),
    onEnterSelection: onEnterSelection
      ? () => onEnterSelection(source.id)
      : undefined,
    onActivate: onClick ? () => onClick(source.id) : undefined,
    longPressDisabled: !onEnterSelection && !selectionMode,
    selectedRingOnly: pipeline.showProgressFill,
  })

  const handleArtifactDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    if (!onArtifactDrop || !isArtifactDragEvent(event)) return
    if (getActiveArtifactDragPayload()?.kind !== 'template') return
    event.preventDefault()
    event.stopPropagation()
    event.dataTransfer.dropEffect = 'copy'
    setIsArtifactDragOver(true)
  }

  const handleArtifactDragEnter = (event: React.DragEvent<HTMLDivElement>) => {
    if (!onArtifactDrop || !isArtifactDragEvent(event)) return
    if (getActiveArtifactDragPayload()?.kind !== 'template') return
    event.stopPropagation()
    setIsArtifactDragOver(true)
  }

  const handleArtifactDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
    if (!onArtifactDrop || !isArtifactDragEvent(event)) return
    if (getActiveArtifactDragPayload()?.kind !== 'template') return
    event.stopPropagation()
    setIsArtifactDragOver(false)
  }

  const handleArtifactDrop = (event: React.DragEvent<HTMLDivElement>) => {
    if (!onArtifactDrop || !isArtifactDragEvent(event)) return
    event.preventDefault()
    event.stopPropagation()
    setIsArtifactDragOver(false)

    const payload = getArtifactDragData(event.dataTransfer)
    clearArtifactDragData()
    if (payload?.kind === 'template') {
      onArtifactDrop(payload.id)
    }
  }

  const badgeTitle =
    pipeline.statusLoading && pipeline.shouldFetchStatus
      ? t('sources.checking')
      : pipeline.statusData?.message || pipeline.statusLabel
  const badgeLabel =
    pipeline.statusLoading && pipeline.shouldFetchStatus
      ? t('sources.checking')
      : pipeline.statusLabel

  const tooltipTitle = isArtifactDragOver
    ? t('sources.dropArtifactOnSource')
    : pipeline.showProgressFill
      ? `${title} — ${pipeline.progressLabel}`
      : title

  return (
    <SourceCardChrome
      rowProps={rowProps}
      selectedClassName={selectedClassName}
      className={className}
      showProgressFill={pipeline.showProgressFill}
      fillPercent={pipeline.fillPercent}
      isFailed={pipeline.isFailed}
      isArtifactDragOver={isArtifactDragOver}
      tooltipTitle={tooltipTitle}
      onDragEnter={handleArtifactDragEnter}
      onDragOver={handleArtifactDragOver}
      onDragLeave={handleArtifactDragLeave}
      onDrop={handleArtifactDrop}
    >
      {selectionMode ? (
        <Checkbox
          checked={selected}
          onCheckedChange={() => onToggleSelect?.(source.id)}
          onClick={(e) => e.stopPropagation()}
          className="shrink-0"
          aria-label={title}
        />
      ) : (
        <SourceTypeIcon
          className={cn(
            'h-3.5 w-3.5 shrink-0 text-muted-foreground',
            sourceIconClassName
          )}
          aria-label={sourceTypeLabel}
        />
      )}

      <h4
        className="min-w-0 flex-1 truncate text-sm font-medium leading-snug"
        title={tooltipTitle}
      >
        {displayTitle}
      </h4>

      <div className="flex shrink-0 items-center gap-0.5">
        <SourceStageActions
          embedState={pipeline.embedState}
          kgState={pipeline.kgState}
          drawingState={showDrawingActions ? pipeline.drawingState : undefined}
          extractReady={pipeline.extractReady}
          embedBusy={pipeline.embedSource.isPending}
          kgBusy={
            pipeline.extractKnowledge.isPending ||
            pipeline.extractKnowledge.isBuilding
          }
          drawingBusy={drawingBusy || pipeline.drawingState === 'running'}
          drawingEligible={drawingEligible}
          embedFailure={pipeline.embedFailure}
          kgFailure={pipeline.kgFailure}
          failureDetailsUnavailable={pipeline.failureDetailsUnavailable}
          onRunEmbeddings={pipeline.handleRunEmbeddings}
          onRunKnowledgeGraph={pipeline.handleBuildKnowledgeGraph}
          onRunDrawingExtraction={
            showDrawingActions
              ? () => onRunDrawingExtraction?.(source.id)
              : undefined
          }
          drawingRunningLabel={
            showDrawingActions
              ? t(drawingProgressLabelKey(pipeline.resolvedDrawingStatus))
              : undefined
          }
          onInspectDrawing={
            drawingRunId && onInspectDrawing
              ? () => onInspectDrawing(drawingRunId)
              : undefined
          }
        />
        <SourceCardStatusBadge
          visible={
            !pipeline.isCompleted && pipeline.pipelineStage === 'extracting'
          }
          colorClassName={pipeline.statusConfig.color}
          icon={StatusIcon}
          isProcessing={pipeline.isProcessing}
          label={badgeLabel}
          title={badgeTitle}
        />
        {!pipeline.isCompleted &&
        pipeline.pipelineStage !== 'extracting' &&
        !selectionMode &&
        pipeline.isProcessing ? (
          <span className="sr-only">{pipeline.statusLabel}</span>
        ) : null}

        {!selectionMode ? (
          <SourceCardActionMenu
            menuOpen={menuOpen}
            onMenuOpenChange={setMenuOpen}
            sourceType={sourceType}
            isCompleted={pipeline.isCompleted}
            isFailed={pipeline.isFailed}
            contextMode={contextMode}
            onContextModeChange={onContextModeChange}
            showRemoveFromProject={showRemoveFromProject}
            onRemoveFromProject={
              onRemoveFromProject
                ? () => onRemoveFromProject(source.id)
                : undefined
            }
            onRetry={onRetry ? () => onRetry(source.id) : undefined}
            onRefreshContent={
              onRefreshContent ? () => onRefreshContent(source.id) : undefined
            }
            kgStatusLoading={pipeline.kgStatusLoading}
            kgBuilding={pipeline.kgBuilding}
            kgFailed={pipeline.kgFailed}
            showBuildKnowledgeGraph={pipeline.showBuildKnowledgeGraph}
            hasKnowledgeGraph={pipeline.hasKnowledgeGraph}
            extractKnowledgeBuilding={pipeline.extractKnowledge.isBuilding}
            onBuildKnowledgeGraph={pipeline.handleBuildKnowledgeGraph}
            showDrawingActions={showDrawingActions}
            drawingEligible={drawingEligible}
            drawingState={pipeline.drawingState}
            drawingBusy={drawingBusy}
            drawingRunId={drawingRunId}
            onRunDrawingExtraction={
              onRunDrawingExtraction
                ? () => onRunDrawingExtraction(source.id)
                : undefined
            }
            onInspectDrawing={
              drawingRunId && onInspectDrawing
                ? () => onInspectDrawing(drawingRunId)
                : undefined
            }
            onDelete={onDelete ? () => onDelete(source.id) : undefined}
          />
        ) : null}
      </div>
    </SourceCardChrome>
  )
}

/**
 * SourceCard is rendered in long lists (one per source). Without memoization, any
 * parent re-render (layout toggles, context-selection changes elsewhere) re-rendered
 * every card, causing UI jank that scaled with the number of sources (#503).
 *
 * We compare only the props that affect this card's rendered output. Handler identity
 * is intentionally ignored: callers often pass inline closures, and those closures
 * capture the source id, so a stale closure stays correct as long as the source data
 * below is unchanged.
 */
function areEqual(prev: SourceCardProps, next: SourceCardProps): boolean {
  if (prev === next) return true

  const p = prev.source as SourceCardListFields
  const n = next.source as SourceCardListFields

  return (
    p.id === n.id &&
    p.title === n.title &&
    p.updated === n.updated &&
    p.status === n.status &&
    p.command_id === n.command_id &&
    p.stage === n.stage &&
    p.pipeline_stage === n.pipeline_stage &&
    p.embedded === n.embedded &&
    p.knowledge_graph === n.knowledge_graph &&
    p.kg_status === n.kg_status &&
    p.drawing_status === n.drawing_status &&
    p.processing_failures === n.processing_failures &&
    p.failure_details_unavailable === n.failure_details_unavailable &&
    p.asset?.url === n.asset?.url &&
    p.asset?.file_path === n.asset?.file_path &&
    topicsEqual(p.topics, n.topics) &&
    prev.projectId === next.projectId &&
    prev.selectionMode === next.selectionMode &&
    prev.selected === next.selected &&
    prev.contextMode === next.contextMode &&
    prev.showRemoveFromProject === next.showRemoveFromProject &&
    prev.className === next.className &&
    prev.drawingStatus === next.drawingStatus &&
    prev.drawingRunId === next.drawingRunId &&
    prev.drawingBusy === next.drawingBusy
  )
}

export const SourceCard = memo(SourceCardImpl, areEqual)
