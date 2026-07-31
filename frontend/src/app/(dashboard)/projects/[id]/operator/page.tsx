'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import {
  ArrowLeft,
  CheckCircle2,
  Loader2,
  Pencil,
  RefreshCw,
  WandSparkles,
  XCircle,
} from 'lucide-react'
import { ProjectHeader } from '../../components/ProjectHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { PageError } from '@/components/common/PageError'
import { DashboardContentSkeleton } from '@/components/layout/DashboardContentSkeleton'
import { useProject } from '@/lib/hooks/use-projects'
import {
  useCorrectProjectSignal,
  useDetectProjectSignals,
  useProjectOperatorInbox,
  useUpdateProjectSignalStatus,
} from '@/lib/hooks/use-project-operator'
import type {
  OperatorInboxItem,
  ProjectSignalStatus,
  SignalSeverity,
} from '@/lib/types/project-operator'
import { cn } from '@/lib/utils'

const severityClasses: Record<SignalSeverity, string> = {
  info: 'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300',
  low: 'border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-300',
  medium: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  high: 'border-orange-500/30 bg-orange-500/10 text-orange-700 dark:text-orange-300',
  critical: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
}

export default function ProjectOperatorPage() {
  const params = useParams()
  const projectId = params?.id ? decodeURIComponent(params.id as string) : ''
  const { data: project, isLoading: projectLoading } = useProject(projectId)
  const { data: inbox, isLoading, error } = useProjectOperatorInbox(projectId)
  const detectSignals = useDetectProjectSignals(projectId)
  const updateStatus = useUpdateProjectSignalStatus(projectId)
  const correctSignal = useCorrectProjectSignal(projectId)
  const [correctingId, setCorrectingId] = useState<string | null>(null)
  const [correctedSummary, setCorrectedSummary] = useState('')
  const [explanation, setExplanation] = useState('')

  if ((projectLoading && !project) || (isLoading && !inbox)) {
    return <DashboardContentSkeleton />
  }

  if (!project) {
    return <PageError title="Project not found" description="The requested project is unavailable." />
  }

  if (error || !inbox) {
    return (
      <PageError
        title="Project Operator unavailable"
        description="The approval inbox could not be loaded."
      />
    )
  }

  const handleStatus = (signalId: string, status: ProjectSignalStatus) => {
    updateStatus.mutate({ signalId, status })
  }

  const submitCorrection = (signalId: string) => {
    if (!correctedSummary.trim() || !explanation.trim()) return
    correctSignal.mutate(
      {
        signalId,
        correction: {
          corrected_summary: correctedSummary.trim(),
          explanation: explanation.trim(),
          actor_id: 'current-user',
        },
      },
      {
        onSuccess: () => {
          setCorrectingId(null)
          setCorrectedSummary('')
          setExplanation('')
        },
      }
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-3 pb-8 sm:px-5">
      <div className="mx-auto w-full max-w-7xl">
        <ProjectHeader
          project={project}
          actions={
            <Button asChild variant="outline" size="sm" className="h-7 px-2 text-xs">
              <Link href={`/projects/${encodeURIComponent(projectId)}`}>
                <ArrowLeft className="h-3.5 w-3.5 sm:mr-1.5" />
                <span className="hidden sm:inline">Project workspace</span>
              </Link>
            </Button>
          }
        />

        <div className="mb-4 flex flex-col gap-3 rounded-lg border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl font-semibold">Project Operator</h1>
            <p className="text-sm text-muted-foreground">
              Review changes, risks, evidence, and recommended actions before anything is executed.
            </p>
          </div>
          <Button
            onClick={() => detectSignals.mutate()}
            disabled={detectSignals.isPending}
            className="w-full sm:w-auto"
          >
            {detectSignals.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Refresh analysis
          </Button>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <InboxSection
            title="What changed"
            emptyText="No new confirmed changes."
            items={inbox.what_changed}
            correctingId={correctingId}
            correctedSummary={correctedSummary}
            explanation={explanation}
            busy={updateStatus.isPending || correctSignal.isPending}
            onStatus={handleStatus}
            onBeginCorrection={(item) => {
              setCorrectingId(item.id)
              setCorrectedSummary(item.title)
              setExplanation('')
            }}
            onCancelCorrection={() => setCorrectingId(null)}
            onCorrectedSummaryChange={setCorrectedSummary}
            onExplanationChange={setExplanation}
            onSubmitCorrection={submitCorrection}
          />
          <InboxSection
            title="Needs attention"
            emptyText="No unresolved high-priority items."
            items={inbox.needs_attention}
            correctingId={correctingId}
            correctedSummary={correctedSummary}
            explanation={explanation}
            busy={updateStatus.isPending || correctSignal.isPending}
            onStatus={handleStatus}
            onBeginCorrection={(item) => {
              setCorrectingId(item.id)
              setCorrectedSummary(item.title)
              setExplanation('')
            }}
            onCancelCorrection={() => setCorrectingId(null)}
            onCorrectedSummaryChange={setCorrectedSummary}
            onExplanationChange={setExplanation}
            onSubmitCorrection={submitCorrection}
          />
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[2fr_1fr]">
          <InboxSection
            title="Recommended actions"
            emptyText="No actions currently require review."
            items={inbox.recommended_actions}
            correctingId={correctingId}
            correctedSummary={correctedSummary}
            explanation={explanation}
            busy={updateStatus.isPending || correctSignal.isPending}
            onStatus={handleStatus}
            onBeginCorrection={(item) => {
              setCorrectingId(item.id)
              setCorrectedSummary(item.title)
              setExplanation('')
            }}
            onCancelCorrection={() => setCorrectingId(null)}
            onCorrectedSummaryChange={setCorrectedSummary}
            onExplanationChange={setExplanation}
            onSubmitCorrection={submitCorrection}
          />

          <section className="rounded-lg border bg-card">
            <div className="border-b px-4 py-3">
              <h2 className="font-semibold">Recent activity</h2>
            </div>
            <div className="divide-y">
              {inbox.recent_activity.length ? (
                inbox.recent_activity.map((activity) => (
                  <div key={activity.id} className="space-y-1 px-4 py-3 text-sm">
                    <div className="font-medium">{activity.event_type}</div>
                    <p className="text-muted-foreground">{activity.reason}</p>
                    <div className="text-xs text-muted-foreground">
                      {activity.actor_type} · {new Date(activity.timestamp).toLocaleString()}
                    </div>
                  </div>
                ))
              ) : (
                <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                  No operator activity yet.
                </p>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

interface InboxSectionProps {
  title: string
  emptyText: string
  items: OperatorInboxItem[]
  correctingId: string | null
  correctedSummary: string
  explanation: string
  busy: boolean
  onStatus: (signalId: string, status: ProjectSignalStatus) => void
  onBeginCorrection: (item: OperatorInboxItem) => void
  onCancelCorrection: () => void
  onCorrectedSummaryChange: (value: string) => void
  onExplanationChange: (value: string) => void
  onSubmitCorrection: (signalId: string) => void
}

function InboxSection({
  title,
  emptyText,
  items,
  correctingId,
  correctedSummary,
  explanation,
  busy,
  onStatus,
  onBeginCorrection,
  onCancelCorrection,
  onCorrectedSummaryChange,
  onExplanationChange,
  onSubmitCorrection,
}: InboxSectionProps) {
  return (
    <section className="rounded-lg border bg-card">
      <div className="border-b px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-semibold">{title}</h2>
          <Badge variant="secondary">{items.length}</Badge>
        </div>
      </div>
      <div className="divide-y">
        {items.length ? (
          items.map((item) => (
            <article key={`${item.section}-${item.id}`} className="space-y-3 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <h3 className="font-medium leading-snug">{item.title}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{item.why_it_matters}</p>
                </div>
                <Badge className={cn('capitalize', severityClasses[item.severity])} variant="outline">
                  {item.severity}
                </Badge>
              </div>

              <div className="rounded-md border bg-muted/30 p-3 text-sm">
                <div className="mb-1 font-medium">Recommended response</div>
                <p className="text-muted-foreground">{item.recommended_action}</p>
              </div>

              <details className="text-sm">
                <summary className="cursor-pointer font-medium">Evidence and affected records</summary>
                <div className="mt-2 space-y-2 rounded-md border p-3 text-xs text-muted-foreground">
                  <div>
                    <span className="font-medium text-foreground">Evidence:</span>{' '}
                    {item.evidence_ids.join(', ')}
                  </div>
                  <div>
                    <span className="font-medium text-foreground">Affected:</span>{' '}
                    {item.affected_entity_ids.join(', ')}
                  </div>
                  <div>Confidence: {Math.round(item.confidence * 100)}%</div>
                </div>
              </details>

              {correctingId === item.id ? (
                <div className="space-y-2 rounded-md border p-3">
                  <label className="block text-xs font-medium">Corrected summary</label>
                  <Textarea
                    value={correctedSummary}
                    onChange={(event) => onCorrectedSummaryChange(event.target.value)}
                    rows={2}
                  />
                  <label className="block text-xs font-medium">Why the signal is incorrect</label>
                  <Textarea
                    value={explanation}
                    onChange={(event) => onExplanationChange(event.target.value)}
                    rows={3}
                  />
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button variant="ghost" size="sm" onClick={onCancelCorrection} disabled={busy}>
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => onSubmitCorrection(item.id)}
                      disabled={busy || !correctedSummary.trim() || !explanation.trim()}
                    >
                      Record correction
                    </Button>
                  </div>
                </div>
              ) : null}

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onStatus(item.id, 'reviewed')}
                  disabled={busy}
                >
                  <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                  Reviewed
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onBeginCorrection(item)}
                  disabled={busy}
                >
                  <Pencil className="mr-1.5 h-3.5 w-3.5" />
                  Correct
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onStatus(item.id, 'converted_to_action')}
                  disabled={busy}
                >
                  <WandSparkles className="mr-1.5 h-3.5 w-3.5" />
                  Prepare action
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onStatus(item.id, 'dismissed')}
                  disabled={busy}
                >
                  <XCircle className="mr-1.5 h-3.5 w-3.5" />
                  Dismiss
                </Button>
              </div>
            </article>
          ))
        ) : (
          <p className="px-4 py-8 text-center text-sm text-muted-foreground">{emptyText}</p>
        )}
      </div>
    </section>
  )
}
