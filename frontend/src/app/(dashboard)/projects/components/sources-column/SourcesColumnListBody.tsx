'use client'

import { DraftingCompass, FileText, Network, RefreshCw, Trash2, Unlink } from 'lucide-react'
import type { SourceListResponse } from '@/lib/types/api'
import type { ContextMode } from '@/lib/types/project-context'
import type { SourceListFilterState } from '@/lib/utils/source-filters'
import { Button } from '@/components/ui/button'
import {
  ColumnCardsSkeleton,
  CompactListRowSkeleton,
} from '@/components/common/LoadingSkeletons'
import { EmptyState } from '@/components/common/EmptyState'
import { ListSelectionBar } from '@/components/common/ListSelectionBar'
import { SourceCard } from '@/components/sources/SourceCard'
import { SourcesFilterBar } from '@/components/sources/SourcesFilterBar'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

export interface SourcesColumnListBodyProps {
  isLoading: boolean
  sources: SourceListResponse[] | undefined
  filteredSources: SourceListResponse[]
  sourceFilters: SourceListFilterState
  onSourceFiltersChange: (filters: SourceListFilterState) => void
  sourceExtensions: string[]
  emptyStateDescription: string
  isArtifactDragOver: boolean
  dropOverlayHint: string
  selectionMode: boolean
  selectedCount: number
  onClearSelection: () => void
  onSelectAllVisible: () => void
  bulkBusy: boolean
  bulkRetryPending: boolean
  onBulkRetryProcessing: () => void
  bulkExtractPending: boolean
  onBulkBuildKnowledgeGraph: () => void
  extractDrawingsPending: boolean
  canExtractDrawings: boolean
  onBulkExtractDrawings: () => void
  onBulkRemoveOpen: () => void
  onBulkDeleteOpen: () => void
  projectId: string
  onSourceClick: (sourceId: string) => void
  onDeleteClick: (sourceId: string) => void
  onRetry: (sourceId: string) => void
  onRemoveFromProject: (sourceId: string) => void
  onRefresh?: () => void
  contextSelections?: Record<string, ContextMode>
  onContextModeChange?: (sourceId: string, mode: ContextMode) => void
  isSelected: (sourceId: string) => boolean
  onToggleSelect: (sourceId: string) => void
  onEnterSelection: (sourceId: string) => void
  drawingRunBySourceId: Map<string, { status: string; runId: string }>
  onRunDrawingExtraction: (sourceId: string) => void
  pendingDrawingSourceIds: Set<string> | null
  isFetchingNextPage?: boolean
}

export function SourcesColumnListBody({
  isLoading,
  sources,
  filteredSources,
  sourceFilters,
  onSourceFiltersChange,
  sourceExtensions,
  emptyStateDescription,
  isArtifactDragOver,
  dropOverlayHint,
  selectionMode,
  selectedCount,
  onClearSelection,
  onSelectAllVisible,
  bulkBusy,
  bulkRetryPending,
  onBulkRetryProcessing,
  bulkExtractPending,
  onBulkBuildKnowledgeGraph,
  extractDrawingsPending,
  canExtractDrawings,
  onBulkExtractDrawings,
  onBulkRemoveOpen,
  onBulkDeleteOpen,
  projectId,
  onSourceClick,
  onDeleteClick,
  onRetry,
  onRemoveFromProject,
  onRefresh,
  contextSelections,
  onContextModeChange,
  isSelected,
  onToggleSelect,
  onEnterSelection,
  drawingRunBySourceId,
  onRunDrawingExtraction,
  pendingDrawingSourceIds,
  isFetchingNextPage,
}: SourcesColumnListBodyProps) {
  const { t } = useTranslation()

  return (
    <>
      {isArtifactDragOver && (
        <div
          className="pointer-events-none absolute inset-1 z-10 flex items-center justify-center rounded-md border-2 border-dashed border-primary bg-primary/5"
          aria-hidden
        >
          <p className="px-4 text-center text-sm font-medium text-primary">
            {dropOverlayHint}
          </p>
        </div>
      )}
      {isLoading ? (
        <ColumnCardsSkeleton count={3} />
      ) : !sources || sources.length === 0 ? (
        <EmptyState
          icon={FileText}
          title={t('sources.noSourcesYet')}
          description={emptyStateDescription}
        />
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <SourcesFilterBar
            filters={sourceFilters}
            onChange={onSourceFiltersChange}
            extensions={sourceExtensions}
          />
          {filteredSources.length === 0 ? (
            <EmptyState
              icon={FileText}
              title={t('sources.filterNoMatches')}
              description={t('common.tryDifferentSearch')}
            />
          ) : (
            <div className="flex flex-col divide-y divide-border/50">
              {selectionMode && (
                <ListSelectionBar
                  count={selectedCount}
                  countLabel={t('sources.selectedCount').replace(
                    '{count}',
                    String(selectedCount)
                  )}
                  onClear={onClearSelection}
                  onSelectAll={onSelectAllVisible}
                >
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-7 shrink-0"
                    disabled={bulkBusy || bulkRetryPending}
                    aria-label={
                      bulkRetryPending
                        ? t('sources.retryingProcessing')
                        : t('sources.retryProcessing')
                    }
                    title={
                      bulkRetryPending
                        ? t('sources.retryingProcessing')
                        : t('sources.retryProcessing')
                    }
                    onClick={() => void onBulkRetryProcessing()}
                  >
                    <RefreshCw
                      className={cn(
                        'size-3.5',
                        bulkRetryPending && 'animate-spin'
                      )}
                    />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-7 shrink-0"
                    disabled={bulkBusy || bulkExtractPending}
                    aria-label={
                      bulkExtractPending
                        ? t('sources.buildingKnowledgeGraph')
                        : t('sources.buildKnowledgeGraph')
                    }
                    title={
                      bulkExtractPending
                        ? t('sources.buildingKnowledgeGraph')
                        : t('sources.buildKnowledgeGraph')
                    }
                    onClick={() => void onBulkBuildKnowledgeGraph()}
                  >
                    <Network className="size-3.5" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-7 shrink-0"
                    disabled={
                      bulkBusy || extractDrawingsPending || !canExtractDrawings
                    }
                    aria-label={
                      extractDrawingsPending
                        ? t('sources.extractingArchitecturalDrawings')
                        : t('sources.extractArchitecturalDrawings')
                    }
                    title={
                      canExtractDrawings
                        ? extractDrawingsPending
                          ? t('sources.extractingArchitecturalDrawings')
                          : t('sources.extractArchitecturalDrawings')
                        : t('sources.drawingExtractPdfOnly')
                    }
                    onClick={() => void onBulkExtractDrawings()}
                  >
                    <DraftingCompass
                      className={cn(
                        'size-3.5',
                        extractDrawingsPending && 'animate-pulse'
                      )}
                    />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-7 shrink-0"
                    aria-label={t('common.bulkRemove')}
                    title={t('common.bulkRemove')}
                    onClick={onBulkRemoveOpen}
                  >
                    <Unlink className="size-3.5" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-7 shrink-0 text-destructive hover:text-destructive"
                    aria-label={t('common.bulkDelete')}
                    title={t('common.bulkDelete')}
                    onClick={onBulkDeleteOpen}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </ListSelectionBar>
              )}
              {filteredSources.map((source) => (
                <SourceCard
                  key={source.id}
                  source={source}
                  projectId={projectId}
                  onClick={onSourceClick}
                  onDelete={onDeleteClick}
                  onRetry={onRetry}
                  onRefreshContent={onRetry}
                  onRemoveFromProject={onRemoveFromProject}
                  onRefresh={onRefresh}
                  showRemoveFromProject={true}
                  contextMode={contextSelections?.[source.id]}
                  onContextModeChange={
                    onContextModeChange
                      ? (mode) => onContextModeChange(source.id, mode)
                      : undefined
                  }
                  selectionMode={selectionMode}
                  selected={isSelected(source.id)}
                  onToggleSelect={onToggleSelect}
                  onEnterSelection={onEnterSelection}
                  drawingStatus={
                    drawingRunBySourceId.get(source.id)?.status ??
                    source.drawing_status
                  }
                  drawingRunId={
                    drawingRunBySourceId.get(source.id)?.runId ?? null
                  }
                  onRunDrawingExtraction={onRunDrawingExtraction}
                  onInspectDrawing={() => onSourceClick(source.id)}
                  drawingBusy={Boolean(pendingDrawingSourceIds?.has(source.id))}
                />
              ))}
              {isFetchingNextPage && <CompactListRowSkeleton />}
            </div>
          )}
        </div>
      )}
    </>
  )
}
