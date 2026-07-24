'use client'

import type { Dispatch, MutableRefObject, SetStateAction } from 'react'
import type { TFunction } from 'i18next'
import { EyeOff, FileText, Plus, Trash2 } from 'lucide-react'
import { CompactListRowSkeleton } from '@/components/common/LoadingSkeletons'
import { EmptyState } from '@/components/common/EmptyState'
import { ListSelectionBar } from '@/components/common/ListSelectionBar'
import { ArtifactListRow } from '@/app/(dashboard)/projects/components/ArtifactListRow'
import { ArtifactTemplatePhases } from '@/app/(dashboard)/projects/components/ArtifactTemplatePhases'
import { ProjectMemorySection } from '@/app/(dashboard)/projects/components/ProjectMemorySection'
import { Button } from '@/components/ui/button'
import {
  ColumnHeader,
  columnHeaderIconClassName,
  columnHeaderPrimaryButtonClassName,
} from '@/components/projects/ColumnHeader'
import type { Artifact } from '@/lib/types/artifacts'
import type { ProjectArtifactResponse } from '@/lib/types/api'
import type { NoteContextMode } from '@/lib/types/project-context'

export interface ArtifactsColumnListBodyProps {
  t: TFunction
  projectId: string
  notes?: ProjectArtifactResponse[]
  isLoading: boolean
  templates: Artifact[]
  templatesLoading: boolean
  onTemplateClick?: (artifactId: string) => void
  contextSelections?: Record<string, NoteContextMode>
  onContextModeChange?: (noteId: string, mode: NoteContextMode) => void
  selectionMode: boolean
  selectedIds: Set<string>
  clearSelection: () => void
  handleSelectAllVisible: () => void
  applyBulkNoteContext: (mode: NoteContextMode) => void
  setBulkDeleteOpen: (open: boolean) => void
  setEditingNote: (note: ProjectArtifactResponse | null) => void
  setShowAddDialog: (open: boolean) => void
  isSelected: (id: string) => boolean
  enterSelection: (id: string) => void
  toggleSelect: (id: string) => void
  onOpenArtifact: (note: ProjectArtifactResponse) => void
  onRenameOpen: (note: ProjectArtifactResponse) => void
  onDeleteClick: (noteId: string) => void
  onIngest: (note: ProjectArtifactResponse) => void | Promise<void>
  onExportPdf: (note: ProjectArtifactResponse) => void | Promise<void>
  onExportMarkdown: (note: ProjectArtifactResponse) => void | Promise<void>
  onReviewFacts: (note: ProjectArtifactResponse) => void | Promise<void>
  onOpenReviewFindings: (note: ProjectArtifactResponse) => void
  reviewPendingNoteId: string | null
  exportPdfPending: boolean
  ingestPending: boolean
  draggingNoteId: string | null
  setDraggingNoteId: Dispatch<SetStateAction<string | null>>
  suppressClickRef: MutableRefObject<boolean>
  unseenIdSet: Set<string>
}

export function ArtifactsColumnListBody(props: ArtifactsColumnListBodyProps) {
  const { t } = props

  return (
    <>
      {(props.templatesLoading || props.templates.length > 0) && (
        <div className="px-1 pt-0.5">
          {props.templatesLoading ? (
            <div className="flex flex-col divide-y divide-border/50">
              {Array.from({ length: 3 }).map((_, i) => (
                <CompactListRowSkeleton key={i} />
              ))}
            </div>
          ) : (
            <ArtifactTemplatePhases
              templates={props.templates}
              onTemplateClick={(artifact) =>
                props.onTemplateClick?.(artifact.id)
              }
            />
          )}
        </div>
      )}

      <ColumnHeader
        title={t('projects.projectArtifacts')}
        actions={
          <Button
            size="sm"
            className={columnHeaderPrimaryButtonClassName}
            onClick={() => {
              props.setEditingNote(null)
              props.setShowAddDialog(true)
            }}
          >
            <Plus className={columnHeaderIconClassName} />
            {t('common.writeNote')}
          </Button>
        }
      />

      <div className="px-1 pb-0.5 pt-0.5">
        {props.isLoading ? (
          <div className="flex flex-col">
            {Array.from({ length: 4 }).map((_, i) => (
              <CompactListRowSkeleton key={i} />
            ))}
          </div>
        ) : !props.notes || props.notes.length === 0 ? (
          <EmptyState
            icon={FileText}
            title={t('projects.noArtifactsYet')}
            description={t('projects.createFirstArtifact')}
          />
        ) : (
          <div className="flex flex-col">
            {props.selectionMode && (
              <ListSelectionBar
                count={props.selectedIds.size}
                countLabel={t('common.selectedItems').replace(
                  '{count}',
                  String(props.selectedIds.size)
                )}
                onClear={props.clearSelection}
                onSelectAll={props.handleSelectAllVisible}
              >
                {props.onContextModeChange && (
                  <>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-7"
                      onClick={() => props.applyBulkNoteContext('full')}
                    >
                      <FileText className="mr-1 h-3.5 w-3.5" />
                      {t('sources.includeAllInContext')}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-7"
                      onClick={() => props.applyBulkNoteContext('off')}
                    >
                      <EyeOff className="mr-1 h-3.5 w-3.5" />
                      {t('sources.excludeAllFromContext')}
                    </Button>
                  </>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 text-destructive hover:text-destructive"
                  onClick={() => props.setBulkDeleteOpen(true)}
                >
                  <Trash2 className="mr-1 h-3.5 w-3.5" />
                  {t('common.bulkDelete')}
                </Button>
              </ListSelectionBar>
            )}
            {props.notes.map((note) => (
              <ArtifactListRow
                key={note.id}
                note={note}
                t={t}
                selectionMode={props.selectionMode}
                selected={props.isSelected(note.id)}
                contextMode={props.contextSelections?.[note.id]}
                onContextModeChange={props.onContextModeChange}
                onEnterSelection={props.enterSelection}
                onToggleSelect={props.toggleSelect}
                onOpen={() => props.onOpenArtifact(note)}
                onRename={() => props.onRenameOpen(note)}
                onDelete={() => props.onDeleteClick(note.id)}
                onIngest={() => void props.onIngest(note)}
                onExportPdf={() => void props.onExportPdf(note)}
                onExportMarkdown={() => void props.onExportMarkdown(note)}
                onReviewFacts={() => void props.onReviewFacts(note)}
                reviewPending={props.reviewPendingNoteId === note.id}
                onOpenReviewFindings={() => props.onOpenReviewFindings(note)}
                exportPdfPending={props.exportPdfPending}
                ingestPending={props.ingestPending}
                draggingNoteId={props.draggingNoteId}
                setDraggingNoteId={props.setDraggingNoteId}
                suppressClickRef={props.suppressClickRef}
                isUnseen={props.unseenIdSet.has(note.id)}
              />
            ))}
          </div>
        )}
      </div>

      <ProjectMemorySection projectId={props.projectId} />
    </>
  )
}
