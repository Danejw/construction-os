'use client'

import type { TFunction } from 'i18next'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { RenameFieldDialog } from '@/components/common/RenameFieldDialog'
import { ArtifactViewerDialog } from '@/app/(dashboard)/projects/components/ArtifactViewerDialog'
import { ArtifactReviewFindingsDialog } from '@/app/(dashboard)/projects/components/ArtifactReviewFindingsDialog'
import { ProjectNoteEditorDialog } from '@/app/(dashboard)/projects/components/ProjectNoteEditorDialog'
import type {
  ArtifactReviewRunResponse,
  ProjectArtifactResponse,
} from '@/lib/types/api'

export interface ArtifactsColumnDialogsProps {
  t: TFunction
  projectId: string
  showAddDialog: boolean
  setShowAddDialog: (open: boolean) => void
  editingNote: ProjectArtifactResponse | null
  setEditingNote: (note: ProjectArtifactResponse | null) => void
  viewingArtifact: ProjectArtifactResponse | null
  setViewingArtifact: (note: ProjectArtifactResponse | null) => void
  displayViewingNote: ProjectArtifactResponse | null | undefined
  viewingNoteLoading: boolean
  renamingNote: ProjectArtifactResponse | null
  setRenamingNote: (note: ProjectArtifactResponse | null) => void
  renameTitle: string
  setRenameTitle: (title: string) => void
  deleteDialogOpen: boolean
  setDeleteDialogOpen: (open: boolean) => void
  bulkDeleteOpen: boolean
  setBulkDeleteOpen: (open: boolean) => void
  findingsNote: ProjectArtifactResponse | null
  setFindingsNote: (note: ProjectArtifactResponse | null) => void
  findingsRun: ArtifactReviewRunResponse | null
  ingestWarnNote: ProjectArtifactResponse | null
  setIngestWarnNote: (note: ProjectArtifactResponse | null) => void
  updatePending: boolean
  deletePending: boolean
  bulkBusy: boolean
  exportPdfPending: boolean
  ingestPending: boolean
  applyReviewPending: boolean
  onExportPdf: (note: ProjectArtifactResponse) => void | Promise<void>
  onExportMarkdown: (note: ProjectArtifactResponse) => void | Promise<void>
  onIngest: (note: ProjectArtifactResponse) => void | Promise<void>
  onIngestWarnConfirm: () => void | Promise<void>
  onApplyReviewFixes: (findingIds: string[]) => void | Promise<void>
  onRenameConfirm: () => void | Promise<void>
  onDeleteConfirm: () => void | Promise<void>
  onBulkDeleteConfirm: () => void | Promise<void>
}

export function ArtifactsColumnDialogs({
  t,
  projectId,
  showAddDialog,
  setShowAddDialog,
  editingNote,
  setEditingNote,
  viewingArtifact,
  setViewingArtifact,
  displayViewingNote,
  viewingNoteLoading,
  renamingNote,
  setRenamingNote,
  renameTitle,
  setRenameTitle,
  deleteDialogOpen,
  setDeleteDialogOpen,
  bulkDeleteOpen,
  setBulkDeleteOpen,
  findingsNote,
  setFindingsNote,
  findingsRun,
  ingestWarnNote,
  setIngestWarnNote,
  updatePending,
  deletePending,
  bulkBusy,
  exportPdfPending,
  ingestPending,
  applyReviewPending,
  onExportPdf,
  onExportMarkdown,
  onIngest,
  onIngestWarnConfirm,
  onApplyReviewFixes,
  onRenameConfirm,
  onDeleteConfirm,
  onBulkDeleteConfirm,
}: ArtifactsColumnDialogsProps) {
  return (
    <>
      <ProjectNoteEditorDialog
        open={showAddDialog || Boolean(editingNote)}
        onOpenChange={(open) => {
          if (!open) {
            setShowAddDialog(false)
            setEditingNote(null)
          } else {
            setShowAddDialog(true)
          }
        }}
        projectId={projectId}
        note={editingNote ?? undefined}
      />

      <ArtifactViewerDialog
        open={Boolean(viewingArtifact)}
        onOpenChange={(open) => !open && setViewingArtifact(null)}
        displayNote={displayViewingNote}
        isLoading={viewingNoteLoading}
        t={t}
        onExportPdf={onExportPdf}
        onExportMarkdown={onExportMarkdown}
        onIngest={onIngest}
        onEdit={(note) => {
          setEditingNote(note)
          setViewingArtifact(null)
        }}
        exportPdfPending={exportPdfPending}
        ingestPending={ingestPending}
      />

      <ArtifactReviewFindingsDialog
        open={Boolean(findingsNote)}
        onOpenChange={(open) => {
          if (!open) setFindingsNote(null)
        }}
        note={findingsNote}
        run={findingsRun}
        onApply={onApplyReviewFixes}
        applyPending={applyReviewPending}
        t={t}
      />

      <RenameFieldDialog
        open={Boolean(renamingNote)}
        onOpenChange={(open) => {
          if (!open) {
            setRenamingNote(null)
            setRenameTitle('')
          }
        }}
        title={t('projects.renameArtifact')}
        label={t('common.title')}
        value={renameTitle}
        onChange={setRenameTitle}
        isSubmitting={updatePending}
        compactFooter
        contentClassName="sm:max-w-md"
        inputId="artifact-rename-title"
        placeholder={t('sources.addTitle')}
        onSubmit={(event) => {
          event.preventDefault()
          void onRenameConfirm()
        }}
      />

      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title={t('projects.deleteArtifact') || t('projects.deleteNote')}
        description={
          t('projects.deleteArtifactConfirm') || t('projects.deleteNoteConfirm')
        }
        confirmText={t('common.delete')}
        onConfirm={() => void onDeleteConfirm()}
        isLoading={deletePending}
        confirmVariant="destructive"
      />

      <ConfirmDialog
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        title={t('projects.deleteArtifact') || t('projects.deleteNote')}
        description={
          t('projects.deleteArtifactConfirm') || t('projects.deleteNoteConfirm')
        }
        confirmText={t('common.delete')}
        onConfirm={() => void onBulkDeleteConfirm()}
        isLoading={bulkBusy}
        confirmVariant="destructive"
      />

      <ConfirmDialog
        open={Boolean(ingestWarnNote)}
        onOpenChange={(open) => {
          if (!open) setIngestWarnNote(null)
        }}
        title={t('projects.reviewIngestWarnTitle')}
        description={t('projects.reviewIngestWarnBody')}
        confirmText={t('projects.reviewIngestWarnConfirm')}
        onConfirm={() => void onIngestWarnConfirm()}
        isLoading={ingestPending}
      />
    </>
  )
}
