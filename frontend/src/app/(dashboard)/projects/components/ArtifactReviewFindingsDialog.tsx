'use client'

import { useEffect, useMemo, useState } from 'react'
import type { TFunction } from 'i18next'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  dialogContentClassName,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type {
  ArtifactReviewClaimFinding,
  ArtifactReviewMemoryFinding,
  ArtifactReviewRunResponse,
  ProjectArtifactResponse,
} from '@/lib/types/api'
import {
  findingHasSuggestedFix,
  parseArtifactReviewFindings,
} from '@/lib/utils/artifact-review-findings'

export interface ArtifactReviewFindingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  note: ProjectArtifactResponse | null
  run: ArtifactReviewRunResponse | null
  onApply: (findingIds: string[]) => void | Promise<void>
  applyPending: boolean
  t: TFunction
}

function FindingRow({
  id,
  title,
  verdict,
  rationale,
  suggestedFix,
  checked,
  selectable,
  onCheckedChange,
}: {
  id: string
  title: string
  verdict: string
  rationale?: string
  suggestedFix?: string | null
  checked: boolean
  selectable: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <li className="rounded-md border border-border/60 px-2 py-1.5">
      <div className="flex items-start gap-2">
        {selectable ? (
          <Checkbox
            checked={checked}
            onCheckedChange={(value) => onCheckedChange(value === true)}
            className="mt-0.5 shrink-0"
            aria-label={title}
            id={`review-finding-${id}`}
          />
        ) : (
          <span className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        )}
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <p className="text-sm font-medium leading-snug">{title}</p>
            <Badge variant="outline" className="text-[10px]">
              {verdict}
            </Badge>
          </div>
          {rationale ? (
            <p className="text-[11px] leading-snug text-muted-foreground">
              {rationale}
            </p>
          ) : null}
          {suggestedFix ? (
            <p className="text-[11px] leading-snug">
              <span className="text-muted-foreground">Fix: </span>
              {suggestedFix}
            </p>
          ) : null}
        </div>
      </div>
    </li>
  )
}

export function ArtifactReviewFindingsDialog({
  open,
  onOpenChange,
  note,
  run,
  onApply,
  applyPending,
  t,
}: ArtifactReviewFindingsDialogProps) {
  const report = useMemo(
    () => parseArtifactReviewFindings(run?.findings),
    [run?.findings]
  )

  const fixableIds = useMemo(() => {
    const ids: string[] = []
    for (const claim of report.claims) {
      if (findingHasSuggestedFix(claim)) ids.push(claim.finding_id)
    }
    for (const memory of report.memory_findings) {
      if (findingHasSuggestedFix(memory)) ids.push(memory.finding_id)
    }
    return ids
  }, [report])

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [pendingApplyIds, setPendingApplyIds] = useState<string[]>([])

  useEffect(() => {
    if (!open) {
      setSelectedIds(new Set())
      setConfirmOpen(false)
      setPendingApplyIds([])
      return
    }
    setSelectedIds(new Set(fixableIds))
  }, [open, run?.id, fixableIds])

  const toggleId = (findingId: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) next.add(findingId)
      else next.delete(findingId)
      return next
    })
  }

  const requestApply = (ids: string[]) => {
    if (ids.length === 0) return
    setPendingApplyIds(ids)
    setConfirmOpen(true)
  }

  const handleConfirmApply = async () => {
    const ids = pendingApplyIds
    setConfirmOpen(false)
    if (ids.length === 0) return
    await onApply(ids)
  }

  const selectedWithFixes = [...selectedIds].filter((id) =>
    fixableIds.includes(id)
  )

  const renderClaim = (claim: ArtifactReviewClaimFinding) => {
    const selectable = findingHasSuggestedFix(claim)
    return (
      <FindingRow
        key={claim.finding_id}
        id={claim.finding_id}
        title={claim.claim_text}
        verdict={claim.source_verdict}
        rationale={claim.rationale}
        suggestedFix={claim.suggested_fix}
        checked={selectedIds.has(claim.finding_id)}
        selectable={selectable}
        onCheckedChange={(checked) => toggleId(claim.finding_id, checked)}
      />
    )
  }

  const renderMemory = (finding: ArtifactReviewMemoryFinding) => {
    const selectable = findingHasSuggestedFix(finding)
    return (
      <FindingRow
        key={finding.finding_id}
        id={finding.finding_id}
        title={finding.claim_text || finding.finding_id}
        verdict={finding.memory_verdict}
        rationale={finding.rationale}
        suggestedFix={finding.suggested_fix}
        checked={selectedIds.has(finding.finding_id)}
        selectable={selectable}
        onCheckedChange={(checked) => toggleId(finding.finding_id, checked)}
      />
    )
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          className={cn(dialogContentClassName, 'sm:max-w-lg')}
        >
          <DialogHeader>
            <DialogTitle>
              {t('projects.reviewFindingsTitle')}
              {note?.title ? ` — ${note.title}` : ''}
            </DialogTitle>
          </DialogHeader>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-1 py-1">
            {run?.stale ? (
              <p className="text-[11px] text-muted-foreground">
                {t('projects.reviewStatusStale')}
              </p>
            ) : null}
            {run?.error_message ? (
              <p className="text-[11px] text-destructive">{run.error_message}</p>
            ) : null}

            <section className="space-y-1.5">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {t('projects.reviewSourceFindings')}
              </h3>
              {report.claims.length === 0 ? (
                <p className="text-[11px] text-muted-foreground">—</p>
              ) : (
                <ul className="space-y-1.5">{report.claims.map(renderClaim)}</ul>
              )}
            </section>

            <section className="space-y-1.5">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {t('projects.reviewMemoryFindings')}
              </h3>
              {report.memory_findings.length === 0 ? (
                <p className="text-[11px] text-muted-foreground">—</p>
              ) : (
                <ul className="space-y-1.5">
                  {report.memory_findings.map(renderMemory)}
                </ul>
              )}
            </section>
          </div>

          <DialogFooter className="gap-1.5 sm:justify-between">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={applyPending || fixableIds.length === 0 || run?.stale}
              onClick={() => requestApply(fixableIds)}
            >
              {t('projects.reviewApplyAll')}
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={
                applyPending ||
                selectedWithFixes.length === 0 ||
                Boolean(run?.stale)
              }
              onClick={() => {
                if (selectedWithFixes.length === 0) return
                requestApply(selectedWithFixes)
              }}
            >
              {t('projects.reviewApplyFix')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t('projects.reviewFindingsTitle')}
        description={
          pendingApplyIds.length === 0
            ? t('projects.reviewNoFixes')
            : t('projects.reviewApplyConfirm')
        }
        confirmText={t('projects.reviewApplyFix')}
        onConfirm={() => void handleConfirmApply()}
        isLoading={applyPending}
      />
    </>
  )
}
