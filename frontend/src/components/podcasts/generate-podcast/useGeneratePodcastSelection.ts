'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQueries, useQueryClient } from '@tanstack/react-query'
import { useProjects } from '@/lib/hooks/use-projects'
import { chatApi } from '@/lib/api/chat'
import { sourcesApi } from '@/lib/api/sources'
import { projectArtifactsApi } from '@/lib/api/project-artifacts'
import {
  BuildContextRequest,
  ProjectArtifactResponse,
  SourceListResponse,
} from '@/lib/types/api'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  getSourceDefaultMode,
  hasSelections,
  type ProjectSelection,
  type ProjectSummary,
  type SourceMode,
} from '@/components/podcasts/generate-podcast/ContentSelectionPanel'

/**
 * Selection, context-count, and content-build state for GeneratePodcastDialog.
 */
export function useGeneratePodcastSelection(open: boolean) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [expandedProjects, setExpandedProjects] = useState<string[]>([])
  const [selections, setSelections] = useState<Record<string, ProjectSelection>>(
    {}
  )
  const [tokenCount, setTokenCount] = useState(0)
  const [charCount, setCharCount] = useState(0)

  const projectsQuery = useProjects()
  const projects = useMemo(
    () => projectsQuery.data ?? [],
    [projectsQuery.data]
  )

  const sourcesQueries = useQueries({
    queries: projects.map((project) => ({
      queryKey: QUERY_KEYS.sources(project.id),
      queryFn: () => sourcesApi.list({ project_id: project.id }),
      enabled:
        open &&
        (expandedProjects.includes(project.id) ||
          hasSelections(selections[project.id])),
    })),
  })

  const notesQueries = useQueries({
    queries: projects.map((project) => ({
      queryKey: QUERY_KEYS.projectArtifacts(project.id),
      queryFn: () => projectArtifactsApi.list({ project_id: project.id }),
      enabled:
        open &&
        (expandedProjects.includes(project.id) ||
          hasSelections(selections[project.id])),
    })),
  })

  const sourcesByProject = useMemo<Record<string, SourceListResponse[]>>(() => {
    const map: Record<string, SourceListResponse[]> = {}
    projects.forEach((project, index) => {
      map[project.id] = sourcesQueries[index]?.data ?? []
    })
    return map
  }, [projects, sourcesQueries])

  const notesByProject = useMemo<
    Record<string, ProjectArtifactResponse[]>
  >(() => {
    const map: Record<string, ProjectArtifactResponse[]> = {}
    projects.forEach((project, index) => {
      map[project.id] = notesQueries[index]?.data ?? []
    })
    return map
  }, [projects, notesQueries])

  const fetchingKey = useMemo(
    () => sourcesQueries.map((q) => (q.isFetching ? '1' : '0')).join(''),
    [sourcesQueries]
  )

  const fetchingProjectIds = useMemo(() => {
    const ids = new Set<string>()
    projects.forEach((project, index) => {
      if (sourcesQueries[index]?.isFetching) {
        ids.add(project.id)
      }
    })
    return ids
  }, [projects, fetchingKey])

  const dataKey = useMemo(() => {
    const sourceIds = sourcesQueries
      .map((q) => q.data?.map((s) => s.id)?.join(',') ?? '')
      .join('|')
    const noteIds = notesQueries
      .map((q) => q.data?.map((n) => n.id)?.join(',') ?? '')
      .join('|')
    return `${sourceIds}::${noteIds}`
  }, [sourcesQueries, notesQueries])

  useEffect(() => {
    if (!open) {
      return
    }

    setSelections((prev) => {
      let changed = false
      const next = { ...prev }

      projects.forEach((project, index) => {
        const sources = sourcesQueries[index]?.data
        const notes = notesQueries[index]?.data

        if (!sources && !notes) {
          return
        }

        if (!next[project.id]) {
          next[project.id] = { sources: {}, notes: {} }
          changed = true
        }

        if (sources) {
          const currentSources = next[project.id].sources
          sources.forEach((source) => {
            if (!(source.id in currentSources)) {
              currentSources[source.id] = getSourceDefaultMode(source)
              changed = true
            }
          })
        }

        if (notes) {
          const currentNotes = next[project.id].notes
          notes.forEach((note) => {
            if (!(note.id in currentNotes)) {
              currentNotes[note.id] = 'full'
              changed = true
            }
          })
        }
      })

      return changed ? next : prev
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projects, dataKey])

  const resetSelectionState = useCallback(() => {
    setExpandedProjects([])
    setSelections({})
    setTokenCount(0)
    setCharCount(0)
  }, [])

  useEffect(() => {
    if (!open) {
      return
    }

    const updateContextCounts = async () => {
      const hasAnySelections = Object.values(selections).some(
        (selection) =>
          Object.values(selection.sources).some((mode) => mode !== 'off') ||
          Object.values(selection.notes).some((mode) => mode !== 'off')
      )

      if (!hasAnySelections) {
        setTokenCount(0)
        setCharCount(0)
        return
      }

      try {
        let totalTokens = 0
        let totalChars = 0

        for (const [projectId, selection] of Object.entries(selections)) {
          const sourcesConfig = Object.entries(selection.sources)
            .filter(([, mode]) => mode !== 'off')
            .reduce<Record<string, string>>((acc, [sourceId]) => {
              const normalizedId = sourceId.replace(/^source:/, '')
              acc[normalizedId] = 'full content'
              return acc
            }, {})

          const notesConfig = Object.entries(selection.notes)
            .filter(([, mode]) => mode !== 'off')
            .reduce<Record<string, string>>((acc, [noteId]) => {
              const normalizedId = noteId.replace(/^note:/, '')
              acc[normalizedId] = 'full content'
              return acc
            }, {})

          if (
            Object.keys(sourcesConfig).length === 0 &&
            Object.keys(notesConfig).length === 0
          ) {
            continue
          }

          const response = await chatApi.buildContext({
            project_id: projectId,
            context_config: {
              sources: sourcesConfig,
              notes: notesConfig,
            },
          })

          totalTokens += response.token_count
          totalChars += response.char_count
        }

        setTokenCount(totalTokens)
        setCharCount(totalChars)
      } catch (error) {
        console.error('Error updating context counts:', error)
      }
    }

    void updateContextCounts()
  }, [open, selections])

  const selectedProjectSummaries = useMemo((): ProjectSummary[] => {
    return projects.map((project) => {
      const selection = selections[project.id]
      if (!selection) {
        return { projectId: project.id, sources: 0, notes: 0 }
      }
      const sourcesCount = Object.values(selection.sources).filter(
        (mode) => mode !== 'off'
      ).length
      const notesCount = Object.values(selection.notes).filter(
        (mode) => mode !== 'off'
      ).length
      return { projectId: project.id, sources: sourcesCount, notes: notesCount }
    })
  }, [projects, selections])

  const handleProjectToggle = useCallback(
    (projectId: string, checked: boolean | 'indeterminate') => {
      const shouldCheck = checked === 'indeterminate' ? true : checked
      const sources = sourcesByProject[projectId] ?? []
      const notes = notesByProject[projectId] ?? []
      setSelections((prev) => {
        if (shouldCheck) {
          const nextSources: Record<string, SourceMode> = {}
          sources.forEach((source) => {
            nextSources[source.id] = getSourceDefaultMode(source)
          })
          const nextNotes: Record<string, SourceMode> = {}
          notes.forEach((note) => {
            nextNotes[note.id] = 'full'
          })
          return {
            ...prev,
            [projectId]: {
              sources: nextSources,
              notes: nextNotes,
            },
          }
        }

        const clearedSources: Record<string, SourceMode> = {}
        sources.forEach((source) => {
          clearedSources[source.id] = 'off'
        })
        const clearedNotes: Record<string, SourceMode> = {}
        notes.forEach((note) => {
          clearedNotes[note.id] = 'off'
        })

        return {
          ...prev,
          [projectId]: {
            sources: clearedSources,
            notes: clearedNotes,
          },
        }
      })
    },
    [notesByProject, sourcesByProject]
  )

  const handleSourceModeChange = useCallback(
    (projectId: string, sourceId: string, mode: SourceMode) => {
      setSelections((prev) => ({
        ...prev,
        [projectId]: {
          sources: {
            ...(prev[projectId]?.sources ?? {}),
            [sourceId]: mode,
          },
          notes: prev[projectId]?.notes ?? {},
        },
      }))
    },
    []
  )

  const handleNoteToggle = useCallback(
    (projectId: string, noteId: string, checked: boolean | 'indeterminate') => {
      setSelections((prev) => ({
        ...prev,
        [projectId]: {
          sources: prev[projectId]?.sources ?? {},
          notes: {
            ...(prev[projectId]?.notes ?? {}),
            [noteId]: checked ? 'full' : 'off',
          },
        },
      }))
    },
    []
  )

  const buildContentFromSelections = useCallback(async () => {
    const parts: string[] = []
    const tasks: Array<{ projectId: string; payload: BuildContextRequest }> = []

    Object.entries(selections).forEach(([projectId, selection]) => {
      const sourcesConfig = Object.entries(selection.sources)
        .filter(([, mode]) => mode !== 'off')
        .reduce<Record<string, string>>((acc, [sourceId]) => {
          const normalizedId = sourceId.replace(/^source:/, '')
          acc[normalizedId] = 'full content'
          return acc
        }, {})

      const notesConfig = Object.entries(selection.notes)
        .filter(([, mode]) => mode !== 'off')
        .reduce<Record<string, string>>((acc, [noteId]) => {
          const normalizedId = noteId.replace(/^note:/, '')
          acc[normalizedId] = 'full content'
          return acc
        }, {})

      if (
        Object.keys(sourcesConfig).length === 0 &&
        Object.keys(notesConfig).length === 0
      ) {
        return
      }

      tasks.push({
        projectId,
        payload: {
          project_id: projectId,
          context_config: {
            sources: sourcesConfig,
            notes: notesConfig,
          },
        },
      })
    })

    if (tasks.length === 0) {
      return ''
    }

    for (const task of tasks) {
      try {
        const response = await chatApi.buildContext(task.payload)
        const projectName =
          projects.find((nb) => nb.id === task.projectId)?.name ?? task.projectId
        const contextString = JSON.stringify(response.context, null, 2)
        const snippet = `${t('common.projectLabel').replace('{name}', projectName)}\n${contextString}`
        parts.push(snippet)
      } catch (error) {
        console.error('Failed to build context for project', task.projectId, error)
        throw new Error(t('podcasts.buildContextFailed'))
      }
    }

    return parts.join('\n\n')
  }, [projects, selections, t])

  return {
    queryClient,
    projects,
    projectsLoading: projectsQuery.isLoading,
    expandedProjects,
    setExpandedProjects,
    selections,
    sourcesByProject,
    notesByProject,
    fetchingProjectIds,
    tokenCount,
    charCount,
    selectedProjectSummaries,
    handleProjectToggle,
    handleSourceModeChange,
    handleNoteToggle,
    buildContentFromSelections,
    resetSelectionState,
  }
}
