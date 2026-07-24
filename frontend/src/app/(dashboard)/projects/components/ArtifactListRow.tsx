'use client'

import { type MutableRefObject } from 'react'
import {
  ArtifactReviewStatus,
  ProjectArtifactResponse,
} from '@/lib/types/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Bot,
  User,
  MoreVertical,
  Trash2,
  FileText,
  Database,
  Pencil,
  Download,
  ShieldCheck,
  Loader2,
} from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import { ContextToggle } from '@/components/common/ContextToggle'
import type { NoteContextMode } from '@/lib/types/project-context'
import { useSelectableRow } from '@/lib/hooks/useSelectableRow'
import { useArtifactReview } from '@/lib/hooks/use-artifact-review'
import { cn } from '@/lib/utils'
import { listActionTriggerClassName } from '@/lib/utils/list-action-trigger'
import { setArtifactDragData, clearArtifactDragData } from '@/lib/utils/artifact-drag'
import {
  isAiArtifact,
  isGeneratedArtifact,
  isManualArtifact,
} from '@/lib/utils/project-artifact-kind'
import { UnreadDot } from '@/components/ui/unread-dot'
import type { TFunction } from 'i18next'

function getArtifactTypeInfo(
  artifact: Pick<ProjectArtifactResponse, 'artifact_kind' | 'note_type'>,
  t: TFunction
) {
  if (isAiArtifact(artifact)) {
    return { icon: Bot, label: t('common.aiGenerated') }
  }
  if (isGeneratedArtifact(artifact)) {
    return { icon: Bot, label: t('navigation.artifact') }
  }
  if (isManualArtifact(artifact)) {
    return { icon: FileText, label: t('navigation.artifact') }
  }
  return { icon: User, label: t('common.human') }
}

export type ArtifactListRowReviewStatus =
  | ArtifactReviewStatus
  | 'stale'
  | null

function resolveReviewStatus(
  status: ArtifactReviewStatus | undefined,
  stale: boolean | undefined
): ArtifactListRowReviewStatus {
  if (!status) return null
  if (status === 'pending' || status === 'running') return status
  if (stale) return 'stale'
  return status
}

function reviewStatusLabel(
  status: NonNullable<ArtifactListRowReviewStatus>,
  t: TFunction
): string {
  switch (status) {
    case 'pending':
    case 'running':
      return t('projects.reviewFactsRunning')
    case 'passed':
      return t('projects.reviewStatusPassed')
    case 'needs_review':
      return t('projects.reviewStatusNeedsReview')
    case 'failed':
      return t('projects.reviewStatusFailed')
    case 'stale':
      return t('projects.reviewStatusStale')
    default: {
      const _exhaustive: never = status
      return _exhaustive
    }
  }
}

export interface ArtifactListRowProps {
  note: ProjectArtifactResponse
  t: TFunction
  selectionMode: boolean
  selected: boolean
  contextMode?: NoteContextMode
  onContextModeChange?: (noteId: string, mode: NoteContextMode) => void
  onEnterSelection: (noteId: string) => void
  onToggleSelect: (noteId: string) => void
  onOpen: () => void
  onRename: () => void
  onDelete: () => void
  onIngest: () => void
  onExportPdf: () => void
  onExportMarkdown: () => void
  exportPdfPending: boolean
  ingestPending: boolean
  draggingNoteId: string | null
  setDraggingNoteId: (id: string | null) => void
  suppressClickRef: MutableRefObject<boolean>
  /** Show a primary unread indicator next to the title. */
  isUnseen?: boolean
  onReviewFacts?: () => void
  reviewPending?: boolean
  /** Override status from parent; when omitted, derived from useArtifactReview. */
  reviewStatus?: ArtifactListRowReviewStatus
  onOpenReviewFindings?: () => void
}

export function ArtifactListRow({
  note,
  t,
  selectionMode,
  selected,
  contextMode,
  onContextModeChange,
  onEnterSelection,
  onToggleSelect,
  onOpen,
  onRename,
  onDelete,
  onIngest,
  onExportPdf,
  onExportMarkdown,
  exportPdfPending,
  ingestPending,
  draggingNoteId,
  setDraggingNoteId,
  suppressClickRef,
  isUnseen = false,
  onReviewFacts,
  reviewPending = false,
  reviewStatus: reviewStatusProp,
  onOpenReviewFindings,
}: ArtifactListRowProps) {
  const { icon: NoteTypeIcon, label: noteTypeLabel } = getArtifactTypeInfo(note, t)
  const title = note.title || t('sources.untitledNote')
  const isIngestibleArtifact = isGeneratedArtifact(note)
  const isDraggingNote = draggingNoteId === note.id

  const { data: review } = useArtifactReview(note.id)
  const derivedStatus = resolveReviewStatus(review?.status, review?.stale)
  const reviewStatus =
    reviewStatusProp !== undefined ? reviewStatusProp : derivedStatus
  const isReviewRunning =
    reviewStatus === 'pending' || reviewStatus === 'running'

  const { rowProps, selectedClassName } = useSelectableRow({
    selectionMode,
    selected,
    onToggleSelect: () => onToggleSelect(note.id),
    onEnterSelection: () => onEnterSelection(note.id),
    onActivate: onOpen,
    suppressClickRef,
  })

  return (
    <div
      {...rowProps}
      draggable={isIngestibleArtifact && !selectionMode}
      aria-grabbed={isDraggingNote}
      className={cn(
        'group relative flex min-w-0 items-center gap-2 rounded-md px-1 py-0.5',
        'cursor-pointer transition-colors select-none',
        'hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
        isIngestibleArtifact && !selectionMode && 'cursor-grab active:cursor-grabbing',
        selectedClassName
      )}
      onDragStart={
        isIngestibleArtifact && !selectionMode
          ? (event) => {
              suppressClickRef.current = false
              setDraggingNoteId(note.id)
              setArtifactDragData(event.dataTransfer, {
                kind: 'note',
                id: note.id,
                title,
              })
            }
          : undefined
      }
      onDrag={
        isIngestibleArtifact && !selectionMode
          ? (event) => {
              if (event.clientX !== 0 || event.clientY !== 0) {
                suppressClickRef.current = true
              }
            }
          : undefined
      }
      onDragEnd={
        isIngestibleArtifact && !selectionMode
          ? () => {
              setDraggingNoteId(null)
              clearArtifactDragData()
              window.setTimeout(() => {
                suppressClickRef.current = false
              }, 0)
            }
          : undefined
      }
    >
      {selectionMode ? (
        <Checkbox
          checked={selected}
          onCheckedChange={() => onToggleSelect(note.id)}
          onClick={(e) => e.stopPropagation()}
          className="shrink-0"
          aria-label={title}
        />
      ) : (
        <NoteTypeIcon
          className={cn(
            'h-3.5 w-3.5 shrink-0',
            isAiArtifact(note) || isGeneratedArtifact(note)
              ? 'text-primary'
              : 'text-muted-foreground'
          )}
          aria-label={noteTypeLabel}
        />
      )}

      <h4
        className="flex min-w-0 flex-1 items-center gap-1.5 text-sm font-medium leading-snug"
        title={title}
      >
        <span className="truncate">{title}</span>
        {isUnseen ? <UnreadDot className="shrink-0" /> : null}
        {reviewStatus ? (
          isReviewRunning ? (
            <Loader2
              className="h-3 w-3 shrink-0 animate-spin text-muted-foreground"
              aria-label={t('projects.reviewFactsRunning')}
            />
          ) : (
            <button
              type="button"
              className="shrink-0 rounded-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              onClick={(e) => {
                e.stopPropagation()
                onOpenReviewFindings?.()
              }}
              aria-label={reviewStatusLabel(reviewStatus, t)}
            >
              <Badge
                variant="outline"
                className={cn(
                  'max-w-[7.5rem] truncate text-[10px] font-normal text-muted-foreground',
                  reviewStatus === 'needs_review' &&
                    'border-amber-500/40 text-amber-700 dark:text-amber-400',
                  reviewStatus === 'failed' &&
                    'border-destructive/40 text-destructive'
                )}
              >
                {reviewStatusLabel(reviewStatus, t)}
              </Badge>
            </button>
          )
        ) : null}
      </h4>

      {!selectionMode && (
        <div className="flex shrink-0 items-center gap-0.5">
          {onContextModeChange && contextMode && (
            <div onClick={(event) => event.stopPropagation()}>
              <ContextToggle
                mode={contextMode}
                onChange={(mode) => onContextModeChange(note.id, mode)}
                className="h-7 w-7"
              />
            </div>
          )}

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className={cn('h-7 w-7 p-0', listActionTriggerClassName)}
                onClick={(e) => e.stopPropagation()}
                aria-label={t('common.actions')}
              >
                <MoreVertical className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              {isIngestibleArtifact ? (
                <>
                  <DropdownMenuSub>
                    <DropdownMenuSubTrigger>
                      <Download className="mr-2 h-4 w-4" />
                      {t('projects.export')}
                    </DropdownMenuSubTrigger>
                    <DropdownMenuSubContent>
                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation()
                          onExportPdf()
                        }}
                        disabled={exportPdfPending}
                      >
                        <FileText className="mr-2 h-4 w-4" />
                        {t('projects.exportPdf')}
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation()
                          onExportMarkdown()
                        }}
                      >
                        <FileText className="mr-2 h-4 w-4" />
                        {t('projects.exportMarkdown')}
                      </DropdownMenuItem>
                    </DropdownMenuSubContent>
                  </DropdownMenuSub>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation()
                      onIngest()
                    }}
                    disabled={ingestPending}
                  >
                    <Database className="h-4 w-4 mr-2" />
                    {t('sources.ingestAsSource')}
                  </DropdownMenuItem>
                </>
              ) : null}
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  onReviewFacts?.()
                }}
                disabled={reviewPending || !onReviewFacts}
              >
                <ShieldCheck className="h-4 w-4 mr-2" />
                {t('projects.reviewFacts')}
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  onRename()
                }}
              >
                <Pencil className="h-4 w-4 mr-2" />
                {t('projects.renameArtifact')}
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete()
                }}
                variant="destructive"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                {t('projects.deleteArtifact') || t('projects.deleteNote')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}
    </div>
  )
}
