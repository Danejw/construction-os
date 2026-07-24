import {
  Clock,
  CheckCircle,
  AlertTriangle,
  Network,
} from 'lucide-react'
import type { TFunction } from 'i18next'
import type { SourceListResponse } from '@/lib/types/api'
import type { StageActionState } from '@/components/sources/SourceStageActions'

/** Discrete pipeline milestones — the card fill width is the only progress UI. */
export const PIPELINE_FILL_PERCENT: Record<string, number> = {
  new: 14,
  queued: 10,
  extracting: 32,
  embedding: 58,
  knowledge_graph: 84,
  running: 32,
}

/** Drawing extraction milestones — same fill-bar treatment as embed / KG. */
export const DRAWING_FILL_PERCENT: Record<string, number> = {
  queued: 8,
  inspecting: 18,
  extracting: 45,
  validating: 78,
  publishing: 90,
}
export type SourceStatus = 'new' | 'queued' | 'running' | 'completed' | 'failed'

export type SourceCardListFields = SourceListResponse & {
  command_id?: string
  status?: string
  stage?: string
  pipeline_stage?: string
}

export function resolvePipelineFillPercent(
  pipelineStage: string | undefined,
  currentStatus: string,
  apiProgress: number | null
): number {
  const stageFloor =
    (pipelineStage && PIPELINE_FILL_PERCENT[pipelineStage]) ||
    PIPELINE_FILL_PERCENT[currentStatus] ||
    16
  if (apiProgress !== null) {
    return Math.min(99, Math.max(apiProgress, stageFloor))
  }
  return stageFloor
}

export function resolveDrawingFillPercent(status: string | null | undefined): number {
  if (!status) return 16
  return DRAWING_FILL_PERCENT[status] ?? 16
}

export function drawingProgressLabelKey(status: string | null | undefined): string {
  switch (status) {
    case 'queued':
      return 'sources.drawingStageQueued'
    case 'inspecting':
      return 'sources.drawingStageInspecting'
    case 'extracting':
      return 'sources.drawingStageExtracting'
    case 'validating':
      return 'sources.drawingStageValidating'
    case 'publishing':
      return 'sources.drawingStagePublishing'
    default:
      return 'sources.drawingRunning'
  }
}

export function getStatusConfig(t: TFunction) {
  return {
    new: {
      icon: Clock,
      color: 'text-primary',
      label: t('sources.statusQueued'),
    },
    queued: {
      icon: Clock,
      color: 'text-primary',
      label: t('sources.statusQueued'),
    },
    running: {
      icon: Clock,
      color: 'text-primary',
      label: t('sources.statusExtracting'),
    },
    extracting: {
      icon: Clock,
      color: 'text-primary',
      label: t('sources.statusExtracting'),
    },
    embedding: {
      icon: Clock,
      color: 'text-primary',
      label: t('sources.statusEmbedding'),
    },
    knowledge_graph: {
      icon: Network,
      color: 'text-primary',
      label: t('sources.statusKnowledgeGraph'),
    },
    completed: {
      icon: CheckCircle,
      color: 'text-green-600 dark:text-green-500',
      label: t('sources.statusCompleted'),
    },
    failed: {
      icon: AlertTriangle,
      color: 'text-destructive',
      label: t('sources.statusFailed'),
    },
  } as const
}

export function isSourceStatus(status: unknown): status is SourceStatus {
  return (
    typeof status === 'string' &&
    ['new', 'queued', 'running', 'completed', 'failed'].includes(status)
  )
}

export function getSourceType(source: SourceListResponse): 'link' | 'upload' | 'text' {
  if (source.asset?.url) return 'link'
  if (source.asset?.file_path) return 'upload'
  return 'text'
}

export function getSourceTypeLabel(
  sourceType: 'link' | 'upload' | 'text',
  t: TFunction
): string {
  if (sourceType === 'link') return t('sources.type.link')
  if (sourceType === 'upload') return t('sources.type.file')
  return t('sources.type.text')
}

export function drawingStageState(status: string | null | undefined): StageActionState {
  if (!status) return 'idle'
  switch (status) {
    case 'completed':
    case 'partial':
      return 'done'
    case 'queued':
    case 'inspecting':
    case 'extracting':
    case 'validating':
    case 'publishing':
      return 'running'
    case 'failed':
      return 'failed'
    case 'skipped':
      return 'idle'
    default:
      return 'idle'
  }
}

export function topicsEqual(a?: string[], b?: string[]): boolean {
  if (a === b) return true
  if ((a?.length ?? 0) !== (b?.length ?? 0)) return false
  if (!a || !b) return true
  return a.every((topic, i) => topic === b[i])
}
