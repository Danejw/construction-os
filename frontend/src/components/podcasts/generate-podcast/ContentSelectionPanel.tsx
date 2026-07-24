'use client'

import { InlineSkeleton, ListRowsSkeleton } from '@/components/common/LoadingSkeletons'
import type { QueryClient } from '@tanstack/react-query'
import { sourcesApi } from '@/lib/api/sources'
import { projectArtifactsApi } from '@/lib/api/project-artifacts'
import { ProjectArtifactResponse, ProjectResponse, SourceListResponse } from '@/lib/types/api'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'

export type SourceMode = 'off' | 'full'

export interface ProjectSelection {
  sources: Record<string, SourceMode>
  notes: Record<string, SourceMode>
}

// Helper function to format large numbers with K/M suffixes
export function formatNumber(num: number): string {
  if (num >= 1000000) {
    return `${(num / 1000000).toFixed(1)}M`
  }
  if (num >= 1000) {
    return `${(num / 1000).toFixed(1)}K`
  }
  return num.toString()
}

export function hasSelections(selection?: ProjectSelection): boolean {
  if (!selection) {
    return false
  }
  return (
    Object.values(selection.sources).some((mode) => mode !== 'off') ||
    Object.values(selection.notes).some((mode) => mode !== 'off')
  )
}

export function getSourceDefaultMode(_source: SourceListResponse): SourceMode {
  return 'full'
}

export interface ProjectSummary {
  projectId: string
  sources: number
  notes: number
}

export interface ContentSelectionPanelProps {
  projects: ProjectResponse[]
  isLoading: boolean
  selectedProjectSummaries: ProjectSummary[]
  tokenCount: number
  charCount: number
  expandedProjects: string[]
  setExpandedProjects: (projects: string[]) => void
  selections: Record<string, ProjectSelection>
  sourcesByProject: Record<string, SourceListResponse[]>
  notesByProject: Record<string, ProjectArtifactResponse[]>
  fetchingProjectIds: Set<string>
  handleProjectToggle: (projectId: string, checked: boolean | 'indeterminate') => void
  handleSourceModeChange: (projectId: string, sourceId: string, mode: SourceMode) => void
  handleNoteToggle: (projectId: string, noteId: string, checked: boolean | 'indeterminate') => void
  queryClient: QueryClient
}

// Extracted component for content selection panel
export function ContentSelectionPanel({
  projects,
  isLoading,
  selectedProjectSummaries,
  tokenCount,
  charCount,
  expandedProjects,
  setExpandedProjects,
  selections,
  sourcesByProject,
  notesByProject,
  fetchingProjectIds,
  handleProjectToggle,
  handleSourceModeChange,
  handleNoteToggle,
  queryClient,
}: ContentSelectionPanelProps) {
  const { t, language } = useTranslation()

  const tr = {
    content: t('podcasts.content'),
    contentDesc: t('podcasts.contentDesc'),
    itemsSelected: t('podcasts.itemsSelected'),
    tokens: t('podcasts.tokens'),
    chars: t('podcasts.chars'),
    loadingProjects: t('podcasts.loadingProjects'),
    noProjectsFoundInPodcasts: t('podcasts.noProjectsFoundInPodcasts'),
    sources: t('podcasts.sources'),
    notes: t('podcasts.notes'),
    noContentSelected: t('podcasts.noContentSelected'),
    noSources: t('podcasts.noSources'),
    untitledSource: t('podcasts.untitledSource'),
    link: t('podcasts.link'),
    file: t('podcasts.file'),
    embedded: t('podcasts.embedded'),
    notEmbedded: t('podcasts.notEmbedded'),
    selectMode: t('podcasts.selectMode'),
    noNotes: t('podcasts.noNotes'),
    untitledNote: t('podcasts.untitledNote'),
    commonUpdated: t('common.updated'),
    summary: t('podcasts.summary'),
    fullContent: t('podcasts.fullContent'),
  }

  const sourceModes = [
    { value: 'full', label: tr.fullContent },
  ] as const

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            {tr.content}
          </h3>
          <p className="text-xs text-muted-foreground">
            {tr.contentDesc}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline">
            {tr.itemsSelected.replace(
              '{count}',
              selectedProjectSummaries.reduce(
                (acc: number, summary: ProjectSummary) => acc + summary.sources + summary.notes,
                0
              ).toString()
            )}
          </Badge>
          {(tokenCount > 0 || charCount > 0) && (
            <span className="text-xs text-muted-foreground">
              {tokenCount > 0 && tr.tokens.replace('{count}', formatNumber(tokenCount))}
              {tokenCount > 0 && charCount > 0 && ' / '}
              {charCount > 0 && tr.chars.replace('{count}', formatNumber(charCount))}
            </span>
          )}
        </div>
      </div>

      <div className="rounded-lg border bg-muted/30">
        {isLoading ? (
          <ListRowsSkeleton rows={5} withHeader={false} />
        ) : projects.length === 0 ? (
          <div className="p-6 text-sm text-muted-foreground">
            {tr.noProjectsFoundInPodcasts}
          </div>
        ) : (
          <ScrollArea className="h-[60vh]">
            <Accordion
              type="multiple"
              value={expandedProjects}
              onValueChange={(value) => setExpandedProjects(value as string[])}
              className="w-full"
            >
              {projects.map((project: ProjectResponse, index: number) => {
                const sources = sourcesByProject[project.id] ?? []
                const notes = notesByProject[project.id] ?? []
                const selection = selections[project.id]
                const summary = selectedProjectSummaries[index]
                const projectChecked = summary.sources + summary.notes > 0
                const totalItems = sources.length + notes.length
                const isIndeterminate =
                  projectChecked &&
                  summary.sources + summary.notes > 0 &&
                  summary.sources + summary.notes < totalItems

                return (
                  <AccordionItem key={project.id} value={project.id}>
                    <div className="flex items-start gap-3 px-4 pt-3">
                      <Checkbox
                        id={`project-toggle-${project.id}`}
                        checked={isIndeterminate ? 'indeterminate' : projectChecked}
                        onCheckedChange={(checked) => {
                          handleProjectToggle(project.id, checked)
                          queryClient.prefetchQuery({
                            queryKey: QUERY_KEYS.sources(project.id),
                            queryFn: () => sourcesApi.list({ project_id: project.id }),
                          })
                          queryClient.prefetchQuery({
                            queryKey: QUERY_KEYS.projectArtifacts(project.id),
                            queryFn: () => projectArtifactsApi.list({ project_id: project.id }),
                          })
                        }}
                        onClick={(event) => event.stopPropagation()}
                      />
                      <AccordionTrigger className="flex-1 px-0 py-0 hover:no-underline">
                        <Label
                          htmlFor={`project-toggle-${project.id}`}
                          className="flex w-full items-center justify-between gap-3 pointer-events-none"
                        >
                          <div className="text-left">
                            <p className="font-medium text-sm text-foreground">
                              {project.name}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {summary.sources + summary.notes > 0
                                ? `${summary.sources} ${tr.sources}, ${summary.notes} ${tr.notes}`
                                : tr.noContentSelected}
                            </p>
                          </div>
                          <Badge variant="outline" className="text-xs">
                            {sources.length} {tr.sources} · {notes.length} {tr.notes}
                          </Badge>
                        </Label>
                      </AccordionTrigger>
                    </div>
                    <AccordionContent>
                      <div className="space-y-4 px-4 pb-4">
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                              {tr.sources}
                            </h4>
                            {fetchingProjectIds.has(project.id) && (
                              <InlineSkeleton className="h-3 w-3" />
                            )}
                          </div>
                          {sources.length === 0 ? (
                            <p className="text-xs text-muted-foreground">
                              {tr.noSources}
                            </p>
                          ) : (
                            <div className="space-y-2">
                              {sources.map((source: SourceListResponse) => {
                                const mode = selection?.sources?.[source.id] ?? 'off'
                                return (
                                  <div
                                    key={source.id}
                                    className="flex items-center gap-3 rounded border bg-background px-3 py-2"
                                  >
                                    <Checkbox
                                      id={`source-selection-${source.id}`}
                                      checked={mode !== 'off'}
                                      onCheckedChange={(checked) =>
                                        handleSourceModeChange(
                                          project.id,
                                          source.id,
                                          checked ? getSourceDefaultMode(source) : 'off'
                                        )
                                      }
                                    />
                                    <Label
                                      htmlFor={`source-selection-${source.id}`}
                                      className="flex flex-1 flex-col gap-1 cursor-pointer"
                                    >
                                      <span className="text-sm font-medium text-foreground">
                                        {source.title || tr.untitledSource}
                                      </span>
                                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                        <span>{source.asset?.url ? tr.link : tr.file}</span>
                                        <span>•</span>
                                        <span>{source.embedded ? tr.embedded : tr.notEmbedded}</span>
                                      </div>
                                    </Label>
                                    <Select
                                      value={mode === 'off' ? 'off' : mode}
                                      onValueChange={(value) =>
                                        handleSourceModeChange(
                                          project.id,
                                          source.id,
                                          value as SourceMode
                                        )
                                      }
                                      disabled={mode === 'off'}
                                    >
                                      <SelectTrigger className="w-[140px]">
                                        <SelectValue placeholder={tr.selectMode} />
                                      </SelectTrigger>
                                      <SelectContent>
                                        {sourceModes.map((option) => (
                                          <SelectItem
                                            key={option.value}
                                            value={option.value}
                                          >
                                            {option.label}
                                          </SelectItem>
                                        ))}
                                      </SelectContent>
                                    </Select>
                                  </div>
                                )
                              })}
                            </div>
                          )}
                        </div>

                        <Separator />

                        <div className="space-y-2">
                          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            {tr.notes}
                          </h4>
                          {notes.length === 0 ? (
                            <p className="text-xs text-muted-foreground">
                              {tr.noNotes}
                            </p>
                          ) : (
                            <div className="space-y-2">
                              {notes.map((note: ProjectArtifactResponse) => {
                                const mode = selection?.notes?.[note.id] ?? 'off'
                                return (
                                  <div
                                    key={note.id}
                                    className="flex items-center gap-3 rounded border bg-background px-3 py-2"
                                  >
                                    <Checkbox
                                      id={`note-selection-${note.id}`}
                                      checked={mode !== 'off'}
                                      onCheckedChange={(checked) =>
                                        handleNoteToggle(
                                          project.id,
                                          note.id,
                                          Boolean(checked)
                                        )
                                      }
                                    />
                                    <Label
                                      htmlFor={`note-selection-${note.id}`}
                                      className="flex flex-1 flex-col cursor-pointer"
                                    >
                                      <span className="text-sm font-medium text-foreground">
                                        {note.title || tr.untitledNote}
                                      </span>
                                      <span className="text-xs text-muted-foreground">
                                        {tr.commonUpdated}{' '}
                                        {new Date(note.updated).toLocaleString(
                                          language.startsWith('zh') ? language : 'en-US'
                                        )}
                                      </span>
                                    </Label>
                                  </div>
                                )
                              })}
                            </div>
                          )}
                        </div>
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                )
              })}
            </Accordion>
          </ScrollArea>
        )}
      </div>
    </div>
  )
}

