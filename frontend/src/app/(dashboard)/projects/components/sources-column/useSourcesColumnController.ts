'use client'

import {
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from 'react'
import type { SourceListResponse } from '@/lib/types/api'
import {
  useDeleteSource,
  useRetrySource,
  useBulkRetrySources,
  useRemoveSourceFromProject,
  useIngestAsSource,
} from '@/lib/hooks/use-sources'
import { useBulkExtractKnowledge } from '@/lib/hooks/use-knowledge'
import {
  useExtractArchitecturalDrawings,
  useProjectDrawingRuns,
} from '@/lib/hooks/use-drawing-extraction'
import { useModalManager } from '@/lib/hooks/use-modal-manager'
import { useListSelection } from '@/lib/hooks/useListSelection'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useProjectColumnsStore } from '@/lib/stores/project-columns-store'
import { createCollapseButton } from '@/components/projects/CollapsibleColumn'
import {
  clearArtifactDragData,
  getActiveArtifactDragPayload,
  getArtifactDragData,
  isArtifactDragEvent,
  type ArtifactDragKind,
} from '@/lib/utils/artifact-drag'
import {
  collectSourceExtensions,
  DEFAULT_SOURCE_LIST_FILTERS,
  isSourceListFilterActive,
  matchesSourceFilters,
  type SourceListFilterState,
} from '@/lib/utils/source-filters'
import type { SourcesViewMode } from '@/app/(dashboard)/projects/components/sources-column/SourcesColumnViewTabs'

export interface UseSourcesColumnControllerArgs {
  sources?: SourceListResponse[]
  projectId: string
  onRefresh?: () => void
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  fetchNextPage?: () => void
  hasArtifactTemplates?: boolean
  hasIngestibleArtifacts?: boolean
}

export function useSourcesColumnController({
  sources,
  projectId,
  onRefresh,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
  hasArtifactTemplates = false,
  hasIngestibleArtifacts = false,
}: UseSourcesColumnControllerArgs) {
  const { t } = useTranslation()
  const [sourcesView, setSourcesView] = useState<SourcesViewMode>('list')
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [isArtifactDragOver, setIsArtifactDragOver] = useState(false)
  const [dragOverKind, setDragOverKind] = useState<ArtifactDragKind | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [sourceToDelete, setSourceToDelete] = useState<string | null>(null)
  const [removeDialogOpen, setRemoveDialogOpen] = useState(false)
  const [sourceToRemove, setSourceToRemove] = useState<string | null>(null)
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)
  const [bulkRemoveOpen, setBulkRemoveOpen] = useState(false)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [sourceFilters, setSourceFilters] = useState<SourceListFilterState>(
    DEFAULT_SOURCE_LIST_FILTERS
  )
  const deferredFilterQuery = useDeferredValue(sourceFilters.query)

  const {
    selectedIds,
    selectionMode,
    selectedList,
    clearSelection,
    enterSelection,
    toggleSelect,
    selectAllVisible,
    isSelected,
  } = useListSelection()

  const { openModal } = useModalManager()
  const deleteSource = useDeleteSource()
  const retrySource = useRetrySource()
  const bulkRetrySources = useBulkRetrySources()
  const removeFromProject = useRemoveSourceFromProject()
  const ingestAsSource = useIngestAsSource()
  const bulkExtractKnowledge = useBulkExtractKnowledge()
  const extractDrawings = useExtractArchitecturalDrawings()
  const { data: drawingRunsData } = useProjectDrawingRuns(projectId)

  const selectedSources = useMemo(
    () => (sources ?? []).filter((s) => selectedIds.has(s.id)),
    [sources, selectedIds]
  )

  const canExtractDrawings = useMemo(() => {
    if (selectedSources.length === 0) return false
    return selectedSources.every((source) => {
      const path = source.asset?.file_path || ''
      return path.toLowerCase().endsWith('.pdf')
    })
  }, [selectedSources])

  const handleBulkExtractDrawings = useCallback(async () => {
    if (selectedList.length === 0 || !canExtractDrawings) return
    setBulkBusy(true)
    try {
      await extractDrawings.mutateAsync({
        source_ids: selectedList,
        project_id: projectId,
        force: false,
      })
      clearSelection()
    } catch (error) {
      console.error('Failed to queue drawing extractions:', error)
    } finally {
      setBulkBusy(false)
    }
  }, [
    selectedList,
    canExtractDrawings,
    extractDrawings,
    projectId,
    clearSelection,
  ])

  const drawingRunBySourceId = useMemo(() => {
    const map = new Map<string, { status: string; runId: string }>()
    for (const run of drawingRunsData?.runs ?? []) {
      const sourceId = String(run.source_id)
      if (map.has(sourceId)) continue
      map.set(sourceId, { status: run.status, runId: run.id })
    }
    return map
  }, [drawingRunsData])

  const effectiveFilters = useMemo(
    () => ({ ...sourceFilters, query: deferredFilterQuery }),
    [sourceFilters, deferredFilterQuery]
  )

  const filteredSources = useMemo(() => {
    const list = sources ?? []
    if (!isSourceListFilterActive(effectiveFilters)) return list
    return list.filter((source) =>
      matchesSourceFilters(source, effectiveFilters, {
        drawingStatus:
          drawingRunBySourceId.get(source.id)?.status ?? source.drawing_status,
      })
    )
  }, [sources, effectiveFilters, drawingRunBySourceId])

  const sourceExtensions = useMemo(
    () => collectSourceExtensions(sources ?? []),
    [sources]
  )

  const handleSelectAllVisible = useCallback(() => {
    selectAllVisible(filteredSources.map((s) => s.id))
  }, [selectAllVisible, filteredSources])

  const handleRunDrawingExtraction = useCallback(
    async (sourceId: string) => {
      try {
        await extractDrawings.mutateAsync({
          source_ids: [sourceId],
          project_id: projectId,
          force: true,
        })
      } catch (error) {
        console.error('Failed to queue drawing extraction:', error)
      }
    },
    [extractDrawings, projectId]
  )

  const pendingDrawingSourceIds = useMemo(() => {
    if (!extractDrawings.isPending) return null
    const ids = extractDrawings.variables?.source_ids
    return ids && ids.length > 0 ? new Set(ids) : null
  }, [extractDrawings.isPending, extractDrawings.variables?.source_ids])

  const handleBulkBuildKnowledgeGraph = useCallback(async () => {
    if (selectedList.length === 0) return
    setBulkBusy(true)
    try {
      await bulkExtractKnowledge.mutateAsync({
        sourceIds: selectedList,
        project_id: projectId,
        extractor: 'generic',
        force: true,
      })
      clearSelection()
    } catch (error) {
      console.error('Failed to queue bulk knowledge graph builds:', error)
    } finally {
      setBulkBusy(false)
    }
  }, [selectedList, bulkExtractKnowledge, projectId, clearSelection])

  const handleBulkRetryProcessing = useCallback(async () => {
    if (selectedList.length === 0) return
    setBulkBusy(true)
    try {
      await bulkRetrySources.mutateAsync(selectedList)
      clearSelection()
    } catch (error) {
      console.error('Failed to bulk retry sources:', error)
    } finally {
      setBulkBusy(false)
    }
  }, [selectedList, bulkRetrySources, clearSelection])

  const enableArtifactDrop = hasArtifactTemplates || hasIngestibleArtifacts
  const { sourcesCollapsed, toggleSources } = useProjectColumnsStore()
  const collapseButton = useMemo(
    () => createCollapseButton(toggleSources, t('navigation.sources')),
    [toggleSources, t]
  )

  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const artifactDragCounterRef = useRef(0)

  const handleArtifactDragEnter = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      if (!enableArtifactDrop || !isArtifactDragEvent(event)) return
      event.preventDefault()
      artifactDragCounterRef.current += 1
      setIsArtifactDragOver(true)
      setDragOverKind(getActiveArtifactDragPayload()?.kind ?? null)
    },
    [enableArtifactDrop]
  )

  const handleArtifactDragLeave = useCallback(() => {
    artifactDragCounterRef.current = Math.max(
      0,
      artifactDragCounterRef.current - 1
    )
    if (artifactDragCounterRef.current === 0) {
      setIsArtifactDragOver(false)
      setDragOverKind(null)
    }
  }, [])

  const handleArtifactDragOver = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      if (!enableArtifactDrop || !isArtifactDragEvent(event)) return
      event.preventDefault()
      event.dataTransfer.dropEffect = 'copy'
      setDragOverKind(getActiveArtifactDragPayload()?.kind ?? null)
    },
    [enableArtifactDrop]
  )

  const handleColumnArtifactDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      if (!enableArtifactDrop) return
      event.preventDefault()
      artifactDragCounterRef.current = 0
      setIsArtifactDragOver(false)
      setDragOverKind(null)

      const payload = getArtifactDragData(event.dataTransfer)
      clearArtifactDragData()
      if (!payload) return

      if (payload.kind === 'note') {
        void ingestAsSource.mutateAsync({
          kind: 'note',
          noteId: payload.id,
          projectId,
        })
        return
      }

      setAddDialogOpen(true)
    },
    [enableArtifactDrop, ingestAsSource, projectId]
  )

  const handleAddDialogOpenChange = useCallback((open: boolean) => {
    setAddDialogOpen(open)
  }, [])

  const emptyStateDescription =
    hasArtifactTemplates || hasIngestibleArtifacts
      ? `${t('sources.createFirstSource')} ${t('sources.dragTemplateToSource')}`
      : t('sources.createFirstSource')

  const dropOverlayHint =
    dragOverKind === 'note'
      ? t('sources.dropArtifactNoteHint')
      : t('sources.dropArtifactHint')

  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container || !hasNextPage || isFetchingNextPage || !fetchNextPage)
      return

    const { scrollTop, scrollHeight, clientHeight } = container
    if (scrollHeight - scrollTop - clientHeight < 200) {
      fetchNextPage()
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return

    container.addEventListener('scroll', handleScroll)
    return () => container.removeEventListener('scroll', handleScroll)
  }, [handleScroll])

  const handleDeleteClick = (sourceId: string) => {
    setSourceToDelete(sourceId)
    setDeleteDialogOpen(true)
  }

  const handleDeleteConfirm = async () => {
    if (!sourceToDelete) return

    try {
      await deleteSource.mutateAsync(sourceToDelete)
      setDeleteDialogOpen(false)
      setSourceToDelete(null)
      onRefresh?.()
    } catch (error) {
      console.error('Failed to delete source:', error)
    }
  }

  const handleRemoveFromProject = (sourceId: string) => {
    setSourceToRemove(sourceId)
    setRemoveDialogOpen(true)
  }

  const handleRemoveConfirm = async () => {
    if (!sourceToRemove) return

    try {
      await removeFromProject.mutateAsync({
        projectId,
        sourceId: sourceToRemove,
      })
      setRemoveDialogOpen(false)
      setSourceToRemove(null)
    } catch (error) {
      console.error('Failed to remove source from project:', error)
    }
  }

  const handleRetry = async (sourceId: string) => {
    try {
      await retrySource.mutateAsync(sourceId)
    } catch (error) {
      console.error('Failed to retry source:', error)
    }
  }

  const handleSourceClick = (sourceId: string) => {
    openModal('source', sourceId)
  }

  const handleBulkDeleteConfirm = async () => {
    setBulkBusy(true)
    try {
      for (const id of selectedList) {
        await deleteSource.mutateAsync(id)
      }
      setBulkDeleteOpen(false)
      clearSelection()
      onRefresh?.()
    } catch (error) {
      console.error('Failed to bulk delete sources:', error)
    } finally {
      setBulkBusy(false)
    }
  }

  const handleBulkRemoveConfirm = async () => {
    setBulkBusy(true)
    try {
      for (const id of selectedList) {
        await removeFromProject.mutateAsync({ projectId, sourceId: id })
      }
      setBulkRemoveOpen(false)
      clearSelection()
    } catch (error) {
      console.error('Failed to bulk remove sources:', error)
    } finally {
      setBulkBusy(false)
    }
  }

  return {
    sourcesView,
    setSourcesView,
    addDialogOpen,
    setAddDialogOpen,
    deleteDialogOpen,
    setDeleteDialogOpen,
    removeDialogOpen,
    setRemoveDialogOpen,
    bulkDeleteOpen,
    setBulkDeleteOpen,
    bulkRemoveOpen,
    setBulkRemoveOpen,
    bulkBusy,
    sourceFilters,
    setSourceFilters,
    selectedIds,
    selectionMode,
    clearSelection,
    enterSelection,
    toggleSelect,
    isSelected,
    canExtractDrawings,
    handleBulkExtractDrawings,
    drawingRunBySourceId,
    pendingDrawingSourceIds,
    filteredSources,
    sourceExtensions,
    handleSelectAllVisible,
    handleRunDrawingExtraction,
    handleBulkBuildKnowledgeGraph,
    handleBulkRetryProcessing,
    enableArtifactDrop,
    sourcesCollapsed,
    toggleSources,
    collapseButton,
    scrollContainerRef,
    isArtifactDragOver,
    handleArtifactDragEnter,
    handleArtifactDragLeave,
    handleArtifactDragOver,
    handleColumnArtifactDrop,
    handleAddDialogOpenChange,
    emptyStateDescription,
    dropOverlayHint,
    handleDeleteClick,
    handleDeleteConfirm,
    handleRemoveFromProject,
    handleRemoveConfirm,
    handleRetry,
    handleSourceClick,
    handleBulkDeleteConfirm,
    handleBulkRemoveConfirm,
    deleteSource,
    removeFromProject,
    bulkRetrySources,
    bulkExtractKnowledge,
    extractDrawings,
  }
}
