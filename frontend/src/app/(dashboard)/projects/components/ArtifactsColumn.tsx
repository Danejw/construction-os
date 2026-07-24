'use client'

import { useState, useMemo, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import {
  ArtifactReviewRunResponse,
  ProjectArtifactResponse,
} from '@/lib/types/api'
import { Card, CardContent } from '@/components/ui/card'
import { FileText } from 'lucide-react'
import { ArtifactsColumnDialogs } from '@/app/(dashboard)/projects/components/artifacts-column/ArtifactsColumnDialogs'
import { ArtifactsColumnListBody } from '@/app/(dashboard)/projects/components/artifacts-column/ArtifactsColumnListBody'
import type { NoteContextMode } from '@/lib/types/project-context'
import {
  useDeleteProjectArtifact,
  useExportProjectArtifactPdf,
  useProjectArtifact,
  useUpdateProjectArtifact,
} from '@/lib/hooks/use-project-artifacts'
import {
  useApplyArtifactReviewFixes,
  useArtifactReview,
  useStartArtifactReview,
} from '@/lib/hooks/use-artifact-review'
import { useArtifacts } from '@/lib/hooks/use-artifacts'
import { useIngestAsSource } from '@/lib/hooks/use-sources'
import { useListSelection } from '@/lib/hooks/useListSelection'
import { useToast } from '@/lib/hooks/use-toast'
import { CollapsibleColumn, createCollapseButton } from '@/components/projects/CollapsibleColumn'
import {
  ColumnHeader,
  columnCardClassName,
} from '@/components/projects/ColumnHeader'
import { useProjectColumnsStore } from '@/lib/stores/project-columns-store'
import { useProjectActivityStore } from '@/lib/stores/project-activity-store'
import { UnreadDot } from '@/components/ui/unread-dot'
import { useTranslation } from '@/lib/hooks/use-translation'
import { downloadArtifactMarkdown, normalizeArtifactId } from '@/lib/utils/export-artifact'
import { projectArtifactsApi } from '@/lib/api/project-artifacts'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { isGeneratedArtifact } from '@/lib/utils/project-artifact-kind'
import { getApiErrorKey } from '@/lib/utils/error-handler'

interface ArtifactsColumnProps {
  notes?: ProjectArtifactResponse[]
  isLoading: boolean
  projectId: string
  contextSelections?: Record<string, NoteContextMode>
  onContextModeChange?: (noteId: string, mode: NoteContextMode) => void
  onTemplateClick?: (artifactId: string) => void
}

async function fetchLatestReviewOrNull(
  noteId: string
): Promise<ArtifactReviewRunResponse | null> {
  try {
    return await projectArtifactsApi.getLatestReview(noteId)
  } catch (error: unknown) {
    if (isAxiosError(error) && error.response?.status === 404) {
      return null
    }
    throw error
  }
}

export function ArtifactsColumn({
  notes,
  isLoading,
  projectId,
  contextSelections,
  onContextModeChange,
  onTemplateClick,
}: ArtifactsColumnProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { data: templates = [], isLoading: templatesLoading } = useArtifacts()
  const [showAddDialog, setShowAddDialog] = useState(false)
  const [editingNote, setEditingNote] = useState<ProjectArtifactResponse | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [noteToDelete, setNoteToDelete] = useState<string | null>(null)
  const [viewingArtifact, setViewingArtifact] = useState<ProjectArtifactResponse | null>(null)
  const [renamingNote, setRenamingNote] = useState<ProjectArtifactResponse | null>(null)
  const [renameTitle, setRenameTitle] = useState('')
  const [draggingNoteId, setDraggingNoteId] = useState<string | null>(null)
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [findingsNote, setFindingsNote] = useState<ProjectArtifactResponse | null>(null)
  const [ingestWarnNote, setIngestWarnNote] = useState<ProjectArtifactResponse | null>(null)
  const suppressClickRef = useRef(false)

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

  const handleSelectAllVisible = useCallback(() => {
    selectAllVisible((notes ?? []).map((n) => n.id))
  }, [selectAllVisible, notes])

  const applyBulkNoteContext = useCallback(
    (mode: NoteContextMode) => {
      if (!onContextModeChange) return
      for (const id of selectedList) {
        onContextModeChange(id, mode)
      }
    },
    [onContextModeChange, selectedList]
  )

  const deleteNote = useDeleteProjectArtifact()
  const updateNote = useUpdateProjectArtifact()
  const exportNotePdf = useExportProjectArtifactPdf()
  const ingestAsSource = useIngestAsSource()
  const startReview = useStartArtifactReview()
  const applyReviewFixes = useApplyArtifactReviewFixes()
  const { toast } = useToast()

  const viewingNoteId = viewingArtifact?.id
    ? normalizeArtifactId(viewingArtifact.id)
    : ''

  const { data: fetchedViewingNote, isLoading: viewingNoteLoading } =
    useProjectArtifact(viewingNoteId, {
      enabled: Boolean(viewingArtifact),
    })

  const displayViewingNote = fetchedViewingNote ?? viewingArtifact

  const findingsNoteId = findingsNote?.id
  const { data: findingsRun = null } = useArtifactReview(findingsNoteId, {
    enabled: Boolean(findingsNoteId),
  })

  const { artifactsCollapsed, toggleArtifacts } = useProjectColumnsStore()
  const unseenArtifactIds = useProjectActivityStore(
    (state) => state.unseenArtifactIdsByProject[projectId] ?? []
  )
  const markArtifactSeen = useProjectActivityStore(
    (state) => state.markArtifactSeen
  )
  const hasUnseenArtifacts = unseenArtifactIds.length > 0
  const unseenIdSet = useMemo(
    () => new Set(unseenArtifactIds),
    [unseenArtifactIds]
  )
  const notesLabel = t('common.artifacts')
  const collapseButton = useMemo(
    () => createCollapseButton(toggleArtifacts, notesLabel),
    [toggleArtifacts, notesLabel]
  )
  const artifactsTitleAdornment = hasUnseenArtifacts ? <UnreadDot /> : undefined

  const handleOpenArtifact = useCallback(
    (note: ProjectArtifactResponse) => {
      markArtifactSeen(projectId, note.id)
      setViewingArtifact(note)
    },
    [markArtifactSeen, projectId]
  )

  const handleDeleteClick = (noteId: string) => {
    setNoteToDelete(noteId)
    setDeleteDialogOpen(true)
  }

  const handleDeleteConfirm = async () => {
    if (!noteToDelete) return
    try {
      await deleteNote.mutateAsync(noteToDelete)
      setDeleteDialogOpen(false)
      setNoteToDelete(null)
    } catch (error) {
      console.error('Failed to delete note:', error)
    }
  }

  const handleBulkDeleteConfirm = async () => {
    setBulkBusy(true)
    try {
      for (const id of selectedList) {
        await deleteNote.mutateAsync(id)
      }
      setBulkDeleteOpen(false)
      clearSelection()
    } catch (error) {
      console.error('Failed to bulk delete artifacts:', error)
    } finally {
      setBulkBusy(false)
    }
  }

  const doIngestNote = async (note: ProjectArtifactResponse) => {
    await ingestAsSource.mutateAsync({
      kind: 'note',
      noteId: note.id,
      projectId,
    })
  }

  const handleIngestNote = async (note: ProjectArtifactResponse) => {
    if (!isGeneratedArtifact(note)) return

    let review = queryClient.getQueryData<ArtifactReviewRunResponse | null>(
      QUERY_KEYS.artifactReview(note.id)
    )

    if (review === undefined) {
      try {
        review = await fetchLatestReviewOrNull(note.id)
        queryClient.setQueryData(QUERY_KEYS.artifactReview(note.id), review)
      } catch (error) {
        console.error('Failed to load artifact review for ingest warn:', error)
        review = null
      }
    }

    if (review && !review.stale && review.status === 'needs_review') {
      setIngestWarnNote(note)
      return
    }

    await doIngestNote(note)
  }

  const handleIngestWarnConfirm = async () => {
    if (!ingestWarnNote) return
    const note = ingestWarnNote
    setIngestWarnNote(null)
    await doIngestNote(note)
  }

  const handleReviewFacts = async (note: ProjectArtifactResponse) => {
    try {
      await startReview.mutateAsync(note.id)
    } catch (error) {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('common.error')),
        variant: 'destructive',
      })
    }
  }

  const handleOpenReviewFindings = (note: ProjectArtifactResponse) => {
    setFindingsNote(note)
  }

  const handleApplyReviewFixes = async (findingIds: string[]) => {
    if (!findingsNote || !findingsRun) return
    if (findingIds.length === 0) {
      toast({
        title: t('common.error'),
        description: t('projects.reviewNoFixes'),
        variant: 'destructive',
      })
      return
    }
    try {
      const result = await applyReviewFixes.mutateAsync({
        noteId: findingsNote.id,
        data: {
          run_id: findingsRun.id,
          finding_ids: findingIds,
        },
      })
      const skipped = result.skipped_spans
      const contentUnchanged =
        (findingsNote.content ?? '') === (result.artifact.content ?? '')
      const allSkipped =
        skipped.length > 0 && skipped.length >= findingIds.length
      if (allSkipped || contentUnchanged) {
        toast({
          title: t('common.warning'),
          description:
            skipped.length > 0
              ? `${t('projects.reviewNoFixes')}: ${skipped.join(', ')}`
              : t('projects.reviewNoFixes'),
        })
        return
      }
      toast({
        title: t('common.success'),
        description:
          skipped.length > 0
            ? `${t('projects.artifactUpdatedSuccess')} (${skipped.join(', ')})`
            : t('projects.artifactUpdatedSuccess'),
      })
    } catch (error) {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('projects.failedToUpdateArtifact')),
        variant: 'destructive',
      })
    }
  }

  const handleExportPdf = async (note: ProjectArtifactResponse) => {
    await exportNotePdf.mutateAsync(note.id)
  }

  const handleExportMarkdown = async (note: ProjectArtifactResponse) => {
    try {
      let title = note.title || ''
      let content = note.content || ''

      if (!content) {
        const fullNote = await projectArtifactsApi.get(
          normalizeArtifactId(note.id)
        )
        title = fullNote.title || title
        content = fullNote.content || ''
      }

      downloadArtifactMarkdown(title, content)
      toast({
        title: t('common.success'),
        description: t('projects.exportMarkdownSuccess'),
      })
    } catch (error) {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('projects.failedToExportMarkdown')),
        variant: 'destructive',
      })
    }
  }

  const handleRenameOpen = (note: ProjectArtifactResponse) => {
    setRenamingNote(note)
    setRenameTitle(note.title || '')
  }

  const handleRenameConfirm = async () => {
    if (!renamingNote) return
    const trimmed = renameTitle.trim()
    if (!trimmed) return
    const noteId = normalizeArtifactId(renamingNote.id)

    try {
      const updated = await updateNote.mutateAsync({
        id: noteId,
        data: { title: trimmed },
      })
      if (viewingArtifact?.id === renamingNote.id) {
        setViewingArtifact(updated)
      }
      setRenamingNote(null)
      setRenameTitle('')
    } catch (error) {
      console.error('Failed to rename artifact:', error)
    }
  }

  const reviewPendingNoteId =
    startReview.isPending && typeof startReview.variables === 'string'
      ? startReview.variables
      : null

  return (
    <>
      <CollapsibleColumn
        isCollapsed={artifactsCollapsed}
        onToggle={toggleArtifacts}
        collapsedIcon={FileText}
        collapsedLabel={notesLabel}
        showUnread={hasUnseenArtifacts}
      >
        <Card className={columnCardClassName}>
          <ColumnHeader
            title={notesLabel}
            titleAdornment={artifactsTitleAdornment}
            actions={collapseButton}
            className="mx-2 my-1 border-b-0"
          />
          <CardContent className="flex min-h-0 flex-1 flex-col overflow-y-auto p-0">
            <ArtifactsColumnListBody
              t={t}
              projectId={projectId}
              notes={notes}
              isLoading={isLoading}
              templates={templates}
              templatesLoading={templatesLoading}
              onTemplateClick={onTemplateClick}
              contextSelections={contextSelections}
              onContextModeChange={onContextModeChange}
              selectionMode={selectionMode}
              selectedIds={selectedIds}
              clearSelection={clearSelection}
              handleSelectAllVisible={handleSelectAllVisible}
              applyBulkNoteContext={applyBulkNoteContext}
              setBulkDeleteOpen={setBulkDeleteOpen}
              setEditingNote={setEditingNote}
              setShowAddDialog={setShowAddDialog}
              isSelected={isSelected}
              enterSelection={enterSelection}
              toggleSelect={toggleSelect}
              onOpenArtifact={handleOpenArtifact}
              onRenameOpen={handleRenameOpen}
              onDeleteClick={handleDeleteClick}
              onIngest={handleIngestNote}
              onExportPdf={handleExportPdf}
              onExportMarkdown={handleExportMarkdown}
              onReviewFacts={handleReviewFacts}
              onOpenReviewFindings={handleOpenReviewFindings}
              reviewPendingNoteId={reviewPendingNoteId}
              exportPdfPending={exportNotePdf.isPending}
              ingestPending={ingestAsSource.isPending}
              draggingNoteId={draggingNoteId}
              setDraggingNoteId={setDraggingNoteId}
              suppressClickRef={suppressClickRef}
              unseenIdSet={unseenIdSet}
            />
          </CardContent>
        </Card>
      </CollapsibleColumn>

      <ArtifactsColumnDialogs
        t={t}
        projectId={projectId}
        showAddDialog={showAddDialog}
        setShowAddDialog={setShowAddDialog}
        editingNote={editingNote}
        setEditingNote={setEditingNote}
        viewingArtifact={viewingArtifact}
        setViewingArtifact={setViewingArtifact}
        displayViewingNote={displayViewingNote}
        viewingNoteLoading={viewingNoteLoading}
        renamingNote={renamingNote}
        setRenamingNote={setRenamingNote}
        renameTitle={renameTitle}
        setRenameTitle={setRenameTitle}
        deleteDialogOpen={deleteDialogOpen}
        setDeleteDialogOpen={setDeleteDialogOpen}
        bulkDeleteOpen={bulkDeleteOpen}
        setBulkDeleteOpen={setBulkDeleteOpen}
        findingsNote={findingsNote}
        setFindingsNote={setFindingsNote}
        findingsRun={findingsRun}
        ingestWarnNote={ingestWarnNote}
        setIngestWarnNote={setIngestWarnNote}
        updatePending={updateNote.isPending}
        deletePending={deleteNote.isPending}
        bulkBusy={bulkBusy}
        exportPdfPending={exportNotePdf.isPending}
        ingestPending={ingestAsSource.isPending}
        applyReviewPending={applyReviewFixes.isPending}
        onExportPdf={handleExportPdf}
        onExportMarkdown={handleExportMarkdown}
        onIngest={handleIngestNote}
        onIngestWarnConfirm={handleIngestWarnConfirm}
        onApplyReviewFixes={handleApplyReviewFixes}
        onRenameConfirm={handleRenameConfirm}
        onDeleteConfirm={handleDeleteConfirm}
        onBulkDeleteConfirm={handleBulkDeleteConfirm}
      />
    </>
  )
}
