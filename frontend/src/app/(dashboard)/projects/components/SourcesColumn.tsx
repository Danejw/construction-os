'use client'

import { Suspense } from 'react'
import { FileText, ListChecks } from 'lucide-react'
import type { SourceListResponse } from '@/lib/types/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { KnowledgeGraphView } from '@/components/knowledge-graph/KnowledgeGraphView'
import type { ContextMode } from '@/lib/types/project-context'
import type { SourceBulkAction } from '@/lib/utils/source-context'
import { CollapsibleColumn } from '@/components/projects/CollapsibleColumn'
import {
  ColumnHeader,
  columnBodyClassName,
  columnCardClassName,
  columnHeaderIconButtonClassName,
  columnHeaderIconClassName,
} from '@/components/projects/ColumnHeader'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'
import { SourcesColumnAddMenu } from '@/app/(dashboard)/projects/components/sources-column/SourcesColumnAddMenu'
import { SourcesColumnDialogs } from '@/app/(dashboard)/projects/components/sources-column/SourcesColumnDialogs'
import { SourcesColumnListBody } from '@/app/(dashboard)/projects/components/sources-column/SourcesColumnListBody'
import { SourcesColumnViewTabs } from '@/app/(dashboard)/projects/components/sources-column/SourcesColumnViewTabs'
import { useSourcesColumnController } from '@/app/(dashboard)/projects/components/sources-column/useSourcesColumnController'

interface SourcesColumnProps {
  sources?: SourceListResponse[]
  isLoading: boolean
  projectId: string
  projectName?: string
  onRefresh?: () => void
  contextSelections?: Record<string, ContextMode>
  onContextModeChange?: (sourceId: string, mode: ContextMode) => void
  onBulkContextModeChange?: (action: SourceBulkAction) => void
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  fetchNextPage?: () => void
  hasArtifactTemplates?: boolean
  hasIngestibleArtifacts?: boolean
}

export function SourcesColumn({
  sources,
  isLoading,
  projectId,
  onRefresh,
  contextSelections,
  onContextModeChange,
  onBulkContextModeChange,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
  hasArtifactTemplates = false,
  hasIngestibleArtifacts = false,
}: SourcesColumnProps) {
  const { t } = useTranslation()
  const c = useSourcesColumnController({
    sources,
    projectId,
    onRefresh,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    hasArtifactTemplates,
    hasIngestibleArtifacts,
  })

  const viewModeTabs = (
    <SourcesColumnViewTabs
      value={c.sourcesView}
      onChange={c.setSourcesView}
    />
  )

  return (
    <>
      <CollapsibleColumn
        isCollapsed={c.sourcesCollapsed}
        onToggle={c.toggleSources}
        collapsedIcon={FileText}
        collapsedLabel={t('navigation.sources')}
      >
        <Card className={columnCardClassName}>
          {c.sourcesView === 'list' ? (
            <ColumnHeader
              title={t('navigation.sources')}
              actions={
                <>
                  {viewModeTabs}
                  {onBulkContextModeChange && sources && sources.length > 0 && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          className={columnHeaderIconButtonClassName}
                          title={t('sources.bulkContext')}
                        >
                          <ListChecks className={columnHeaderIconClassName} />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onClick={() => onBulkContextModeChange('full')}
                        >
                          {t('sources.includeAllFull')}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => onBulkContextModeChange('exclude')}
                        >
                          {t('sources.excludeAllFromContext')}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                  <SourcesColumnAddMenu
                    onAddSource={() => c.setAddDialogOpen(true)}
                  />
                  {c.collapseButton}
                </>
              }
            />
          ) : null}

          <CardContent
            ref={c.sourcesView === 'list' ? c.scrollContainerRef : undefined}
            className={cn(
              columnBodyClassName,
              'relative',
              c.sourcesView === 'graph' && 'overflow-hidden p-0'
            )}
            onDragEnter={
              c.sourcesView === 'list' && c.enableArtifactDrop
                ? c.handleArtifactDragEnter
                : undefined
            }
            onDragLeave={
              c.sourcesView === 'list' && c.enableArtifactDrop
                ? c.handleArtifactDragLeave
                : undefined
            }
            onDragOver={
              c.sourcesView === 'list' && c.enableArtifactDrop
                ? c.handleArtifactDragOver
                : undefined
            }
            onDrop={
              c.sourcesView === 'list' && c.enableArtifactDrop
                ? c.handleColumnArtifactDrop
                : undefined
            }
          >
            {c.sourcesView === 'graph' ? (
              <Suspense
                fallback={
                  <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                    {t('knowledge.graphLoading')}
                  </div>
                }
              >
                <KnowledgeGraphView
                  projectId={projectId}
                  embedded
                  headerLeading={viewModeTabs}
                  headerTrailing={
                    <SourcesColumnAddMenu
                      onAddSource={() => c.setAddDialogOpen(true)}
                      variant="icon"
                    />
                  }
                />
              </Suspense>
            ) : (
              <SourcesColumnListBody
                isLoading={isLoading}
                sources={sources}
                filteredSources={c.filteredSources}
                sourceFilters={c.sourceFilters}
                onSourceFiltersChange={c.setSourceFilters}
                sourceExtensions={c.sourceExtensions}
                emptyStateDescription={c.emptyStateDescription}
                isArtifactDragOver={c.isArtifactDragOver}
                dropOverlayHint={c.dropOverlayHint}
                selectionMode={c.selectionMode}
                selectedCount={c.selectedIds.size}
                onClearSelection={c.clearSelection}
                onSelectAllVisible={c.handleSelectAllVisible}
                bulkBusy={c.bulkBusy}
                bulkRetryPending={c.bulkRetrySources.isPending}
                onBulkRetryProcessing={c.handleBulkRetryProcessing}
                bulkExtractPending={c.bulkExtractKnowledge.isPending}
                onBulkBuildKnowledgeGraph={c.handleBulkBuildKnowledgeGraph}
                extractDrawingsPending={c.extractDrawings.isPending}
                canExtractDrawings={c.canExtractDrawings}
                onBulkExtractDrawings={c.handleBulkExtractDrawings}
                onBulkRemoveOpen={() => c.setBulkRemoveOpen(true)}
                onBulkDeleteOpen={() => c.setBulkDeleteOpen(true)}
                projectId={projectId}
                onSourceClick={c.handleSourceClick}
                onDeleteClick={c.handleDeleteClick}
                onRetry={c.handleRetry}
                onRemoveFromProject={c.handleRemoveFromProject}
                onRefresh={onRefresh}
                contextSelections={contextSelections}
                onContextModeChange={onContextModeChange}
                isSelected={c.isSelected}
                onToggleSelect={c.toggleSelect}
                onEnterSelection={c.enterSelection}
                drawingRunBySourceId={c.drawingRunBySourceId}
                onRunDrawingExtraction={c.handleRunDrawingExtraction}
                pendingDrawingSourceIds={c.pendingDrawingSourceIds}
                isFetchingNextPage={isFetchingNextPage}
              />
            )}
          </CardContent>
        </Card>
      </CollapsibleColumn>

      <SourcesColumnDialogs
        projectId={projectId}
        addDialogOpen={c.addDialogOpen}
        onAddDialogOpenChange={c.handleAddDialogOpenChange}
        deleteDialogOpen={c.deleteDialogOpen}
        onDeleteDialogOpenChange={c.setDeleteDialogOpen}
        onDeleteConfirm={c.handleDeleteConfirm}
        deleteLoading={c.deleteSource.isPending}
        removeDialogOpen={c.removeDialogOpen}
        onRemoveDialogOpenChange={c.setRemoveDialogOpen}
        onRemoveConfirm={c.handleRemoveConfirm}
        removeLoading={c.removeFromProject.isPending}
        bulkDeleteOpen={c.bulkDeleteOpen}
        onBulkDeleteOpenChange={c.setBulkDeleteOpen}
        onBulkDeleteConfirm={c.handleBulkDeleteConfirm}
        bulkRemoveOpen={c.bulkRemoveOpen}
        onBulkRemoveOpenChange={c.setBulkRemoveOpen}
        onBulkRemoveConfirm={c.handleBulkRemoveConfirm}
        bulkBusy={c.bulkBusy}
      />
    </>
  )
}
