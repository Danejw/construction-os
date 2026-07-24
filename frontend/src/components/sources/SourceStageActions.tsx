'use client'

import { useState } from 'react'
import { Database, DraftingCompass, Network, RefreshCw, Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Popover,
  PopoverAnchor,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { InlineSkeleton } from '@/components/common/LoadingSkeletons'
import { useTranslation } from '@/lib/hooks/use-translation'
import { clearBodyPointerLock } from '@/lib/utils/clear-body-pointer-lock'
import { cn } from '@/lib/utils'
import type { SourceProcessingFailure } from '@/lib/types/api'

export type StageActionState = 'idle' | 'running' | 'done' | 'failed'

type StageKind = 'embed' | 'kg' | 'drawing'

type StagePanel = 'failure' | 'confirm-start' | 'confirm-rerun'

interface SourceStageActionsProps {
  embedState: StageActionState
  kgState: StageActionState
  drawingState?: StageActionState
  extractReady: boolean
  embedBusy: boolean
  kgBusy: boolean
  drawingBusy?: boolean
  drawingEligible?: boolean
  embedFailure?: SourceProcessingFailure
  kgFailure?: SourceProcessingFailure
  failureDetailsUnavailable?: boolean
  onRunEmbeddings: () => void
  onRunKnowledgeGraph: () => void
  onRunDrawingExtraction?: () => void
  onInspectDrawing?: () => void
  /** Overrides the generic drawing running tooltip with the live step name. */
  drawingRunningLabel?: string
}

/**
 * Compact embeddings + knowledge-graph (+ optional drawing) controls for the source list row.
 * Incomplete/failed → confirm popover next to the icon, then run. Completed → re-run menu → confirm.
 */
export function SourceStageActions({
  embedState,
  kgState,
  drawingState,
  extractReady,
  embedBusy,
  kgBusy,
  drawingBusy = false,
  drawingEligible = true,
  embedFailure,
  kgFailure,
  failureDetailsUnavailable = false,
  onRunEmbeddings,
  onRunKnowledgeGraph,
  onRunDrawingExtraction,
  onInspectDrawing,
  drawingRunningLabel,
}: SourceStageActionsProps) {
  const { t } = useTranslation()

  return (
    <>
      <StageIconButton
        kind="embed"
        state={embedState}
        disabled={!extractReady || embedState === 'running' || embedBusy}
        busy={embedBusy}
        doneLabel={t('sources.embeddingsDone')}
        runningLabel={t('sources.embeddingsRunning')}
        failedLabel={t('sources.embeddingsFailed')}
        idleLabel={t('sources.embeddingsMissing')}
        rerunLabel={t('sources.embeddingsRerun')}
        retryLabel={t('sources.retry')}
        confirmTitle={t('sources.embeddingsConfirmTitle')}
        confirmDescription={t('sources.embeddingsConfirmDesc')}
        rerunConfirmTitle={t('sources.embeddingsRerunTitle')}
        rerunConfirmDescription={t('sources.embeddingsRerunDesc')}
        failure={embedFailure}
        failureDetailsUnavailable={failureDetailsUnavailable}
        unavailableLabel={t('sources.failureDetailsUnavailable')}
        errorDetailsLabel={t('common.errorDetails')}
        onConfirm={onRunEmbeddings}
      />
      <StageIconButton
        kind="kg"
        state={kgState}
        disabled={
          !extractReady ||
          kgState === 'running' ||
          kgBusy ||
          (kgState !== 'done' && embedState !== 'done')
        }
        busy={kgBusy}
        doneLabel={t('sources.knowledgeGraphDone')}
        runningLabel={t('sources.knowledgeGraphRunning')}
        failedLabel={t('sources.knowledgeGraphFailed')}
        idleLabel={
          embedState !== 'done'
            ? t('sources.knowledgeGraphNeedsEmbeddings')
            : t('sources.knowledgeGraphMissing')
        }
        rerunLabel={t('sources.knowledgeGraphRerun')}
        retryLabel={t('sources.retry')}
        confirmTitle={t('sources.knowledgeGraphConfirmTitle')}
        confirmDescription={t('sources.knowledgeGraphConfirmDesc')}
        rerunConfirmTitle={t('sources.knowledgeGraphRerunTitle')}
        rerunConfirmDescription={t('sources.knowledgeGraphRerunDesc')}
        failure={kgFailure}
        failureDetailsUnavailable={failureDetailsUnavailable}
        unavailableLabel={t('sources.failureDetailsUnavailable')}
        errorDetailsLabel={t('common.errorDetails')}
        onConfirm={onRunKnowledgeGraph}
      />
      {drawingState !== undefined && onRunDrawingExtraction ? (
        <StageIconButton
          kind="drawing"
          state={drawingState}
          disabled={
            drawingState === 'running' ||
            drawingBusy ||
            (!drawingEligible && drawingState !== 'done')
          }
          busy={drawingBusy}
          doneLabel={t('sources.drawingDone')}
          runningLabel={drawingRunningLabel ?? t('sources.drawingRunning')}
          failedLabel={t('sources.drawingFailed')}
          idleLabel={
            drawingEligible
              ? t('sources.drawingMissing')
              : t('sources.drawingPdfOnly')
          }
          rerunLabel={t('sources.drawingRerun')}
          retryLabel={t('sources.retry')}
          confirmTitle={t('sources.drawingConfirmTitle')}
          confirmDescription={t('sources.drawingConfirmDesc')}
          rerunConfirmTitle={t('sources.drawingRerunTitle')}
          rerunConfirmDescription={t('sources.drawingRerunDesc')}
          failureDetailsUnavailable={false}
          unavailableLabel={t('sources.failureDetailsUnavailable')}
          errorDetailsLabel={t('common.errorDetails')}
          inspectLabel={t('sources.drawingInspectResults')}
          onConfirm={onRunDrawingExtraction}
          onInspect={onInspectDrawing}
        />
      ) : null}
    </>
  )
}

function stageIcon(kind: StageKind) {
  switch (kind) {
    case 'embed':
      return Database
    case 'kg':
      return Network
    case 'drawing':
      return DraftingCompass
    default: {
      const _exhaustive: never = kind
      return _exhaustive
    }
  }
}

function StageConfirmBody({
  title,
  description,
  busy,
  onCancel,
  onConfirm,
}: {
  title: string
  description: string
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3 p-3">
      <div className="space-y-1">
        <p className="text-sm font-medium leading-none">{title}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={(e) => {
            e.stopPropagation()
            onCancel()
          }}
        >
          {t('common.cancel')}
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={busy}
          onClick={(e) => {
            e.stopPropagation()
            onConfirm()
          }}
        >
          {busy ? (
            <>
              <InlineSkeleton className="mr-2" />
              {t('common.confirm')}
            </>
          ) : (
            t('common.confirm')
          )}
        </Button>
      </div>
    </div>
  )
}

function StageIconButton({
  state,
  disabled,
  busy,
  doneLabel,
  runningLabel,
  failedLabel,
  idleLabel,
  rerunLabel,
  retryLabel,
  confirmTitle,
  confirmDescription,
  rerunConfirmTitle,
  rerunConfirmDescription,
  failure,
  failureDetailsUnavailable,
  unavailableLabel,
  errorDetailsLabel,
  inspectLabel,
  onConfirm,
  onInspect,
  kind,
}: {
  kind: StageKind
  state: StageActionState
  disabled: boolean
  busy: boolean
  doneLabel: string
  runningLabel: string
  failedLabel: string
  idleLabel: string
  rerunLabel: string
  retryLabel: string
  confirmTitle: string
  confirmDescription: string
  rerunConfirmTitle: string
  rerunConfirmDescription: string
  failure?: SourceProcessingFailure
  failureDetailsUnavailable: boolean
  unavailableLabel: string
  errorDetailsLabel: string
  inspectLabel?: string
  onConfirm: () => void
  onInspect?: () => void
}) {
  const [panel, setPanel] = useState<StagePanel | null>(null)
  const Icon = stageIcon(kind)
  const colorClass =
    state === 'done'
      ? 'text-emerald-600'
      : state === 'running'
        ? 'text-primary'
        : state === 'failed'
          ? 'text-destructive'
          : 'text-muted-foreground'

  const title =
    state === 'done'
      ? doneLabel
      : state === 'running'
        ? runningLabel
        : state === 'failed'
          ? failedLabel
          : idleLabel

  const icon = (
    <Icon
      className={cn('h-3.5 w-3.5', state === 'running' && 'animate-pulse')}
    />
  )

  const panelOpen = panel !== null

  const closePanel = () => {
    setPanel(null)
    clearBodyPointerLock()
  }

  const runConfirmed = () => {
    closePanel()
    window.setTimeout(() => {
      clearBodyPointerLock()
      onConfirm()
    }, 0)
  }

  const confirmCopy =
    panel === 'confirm-rerun'
      ? { title: rerunConfirmTitle, description: rerunConfirmDescription }
      : { title: confirmTitle, description: confirmDescription }

  const confirmPopover =
    panel === 'confirm-start' || panel === 'confirm-rerun' ? (
      <PopoverContent
        align="end"
        side="bottom"
        sideOffset={6}
        className="w-72 p-0"
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
        onCloseAutoFocus={(e) => {
          e.preventDefault()
          clearBodyPointerLock()
        }}
      >
        <StageConfirmBody
          title={confirmCopy.title}
          description={confirmCopy.description}
          busy={busy}
          onCancel={closePanel}
          onConfirm={runConfirmed}
        />
      </PopoverContent>
    ) : null

  if (state === 'failed') {
    return (
      <Popover
        open={panelOpen}
        onOpenChange={(open) => {
          if (!open) {
            closePanel()
            return
          }
          setPanel('failure')
        }}
      >
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={cn('h-6 w-6 p-0', colorClass)}
            title={title}
            aria-label={title}
            onClick={(e) => e.stopPropagation()}
            onPointerDown={(e) => e.stopPropagation()}
          >
            {icon}
          </Button>
        </PopoverTrigger>
        {panel === 'failure' ? (
          <PopoverContent
            align="end"
            className="w-80 space-y-2 p-2"
            onClick={(e) => e.stopPropagation()}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <p className="text-xs font-medium text-destructive">
              {errorDetailsLabel}: {failedLabel}
            </p>
            <p className="break-words text-xs">
              {failure?.message ??
                (failureDetailsUnavailable ? unavailableLabel : failedLabel)}
            </p>
            {failure && (
              <div className="flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                {failure.error_type && <span>{failure.error_type}</span>}
                {failure.occurred_at && (
                  <time dateTime={failure.occurred_at}>
                    {new Date(failure.occurred_at).toLocaleString()}
                  </time>
                )}
                {failure.command_id && (
                  <code className="break-all">{failure.command_id}</code>
                )}
              </div>
            )}
            <Button
              type="button"
              size="sm"
              className="w-full"
              onClick={(e) => {
                e.stopPropagation()
                setPanel('confirm-start')
              }}
            >
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              {retryLabel}
            </Button>
          </PopoverContent>
        ) : (
          confirmPopover
        )}
      </Popover>
    )
  }

  if (state === 'done') {
    return (
      <Popover
        open={panel === 'confirm-rerun'}
        onOpenChange={(open) => {
          if (!open) closePanel()
        }}
      >
        <PopoverAnchor asChild>
          <span className="inline-flex">
            <DropdownMenu modal={false}>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className={cn('h-6 w-6 p-0', colorClass)}
                  title={title}
                  aria-label={title}
                  onClick={(e) => e.stopPropagation()}
                  onPointerDown={(e) => e.stopPropagation()}
                >
                  {icon}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                onClick={(e) => e.stopPropagation()}
                onCloseAutoFocus={(e) => {
                  e.preventDefault()
                  clearBodyPointerLock()
                }}
              >
                {onInspect && inspectLabel ? (
                  <DropdownMenuItem
                    onSelect={(e) => {
                      e.preventDefault()
                      onInspect()
                    }}
                  >
                    <Eye className="mr-2 h-3.5 w-3.5" />
                    {inspectLabel}
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuItem
                  onSelect={(e) => {
                    e.preventDefault()
                    window.setTimeout(() => {
                      clearBodyPointerLock()
                      setPanel('confirm-rerun')
                    }, 0)
                  }}
                >
                  <RefreshCw className="mr-2 h-3.5 w-3.5" />
                  {rerunLabel}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </span>
        </PopoverAnchor>
        {confirmPopover}
      </Popover>
    )
  }

  return (
    <Popover
      open={panel === 'confirm-start'}
      onOpenChange={(open) => {
        if (!open) closePanel()
      }}
    >
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={cn('h-6 w-6 p-0', colorClass)}
          title={title}
          aria-label={title}
          disabled={disabled}
          onClick={(e) => {
            e.stopPropagation()
            if (!disabled) setPanel('confirm-start')
          }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          {icon}
        </Button>
      </PopoverTrigger>
      {confirmPopover}
    </Popover>
  )
}
