import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectArtifactsApi } from '@/lib/api/project-artifacts'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import {
  buildOptimisticProjectArtifact,
  patchAllProjectArtifactListQueries,
  prependProjectArtifactToProjectQuery,
  removeProjectArtifactFromAllQueries,
  restoreProjectArtifactListQueries,
  snapshotProjectArtifactListQueries,
} from '@/lib/utils/project-artifact-query-cache'
import {
  CreateProjectArtifactRequest,
  ProjectArtifactResponse,
  UpdateProjectArtifactRequest,
} from '@/lib/types/api'

export function useProjectArtifacts(projectId?: string) {
  return useQuery({
    queryKey: QUERY_KEYS.projectArtifacts(projectId),
    queryFn: () => projectArtifactsApi.list({ project_id: projectId }),
    enabled: !!projectId,
  })
}

export function useProjectArtifact(id?: string, options?: { enabled?: boolean }) {
  const artifactId = id ?? ''
  return useQuery({
    queryKey: QUERY_KEYS.projectArtifact(artifactId),
    queryFn: () => projectArtifactsApi.get(artifactId),
    enabled: !!artifactId && (options?.enabled ?? true),
  })
}

export function useCreateProjectArtifact() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: CreateProjectArtifactRequest) => projectArtifactsApi.create(data),
    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: ['projectArtifacts'] })
      const previous = snapshotProjectArtifactListQueries(queryClient)
      const optimistic = buildOptimisticProjectArtifact(variables)
      prependProjectArtifactToProjectQuery(queryClient, variables.project_id, optimistic)
      return { previous, optimisticId: optimistic.id, projectId: variables.project_id }
    },
    onSuccess: (result, variables, context) => {
      if (context?.optimisticId) {
        patchAllProjectArtifactListQueries(queryClient, (artifacts) =>
          artifacts.map((artifact) =>
            artifact.id === context.optimisticId ? result : artifact
          )
        )
        if (variables.project_id) {
          queryClient.setQueryData(QUERY_KEYS.projectArtifact(result.id), result)
        }
      }
      toast({
        title: t('common.success'),
        description: t('projects.artifactCreatedSuccess'),
      })
    },
    onError: (error: unknown, _variables, context) => {
      if (context?.previous) {
        restoreProjectArtifactListQueries(queryClient, context.previous)
      }
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, t, 'projects.failedToCreateArtifact'),
        variant: 'destructive',
      })
    },
    onSettled: (_data, _error, variables) => {
      if (variables.project_id) {
        queryClient.invalidateQueries({
          queryKey: QUERY_KEYS.projectArtifacts(variables.project_id),
        })
      }
    },
  })
}

export function useUpdateProjectArtifact() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateProjectArtifactRequest }) =>
      projectArtifactsApi.update(id, data),
    onMutate: async ({ id, data }) => {
      await queryClient.cancelQueries({ queryKey: ['projectArtifacts'] })
      const previousLists = snapshotProjectArtifactListQueries(queryClient)
      const previousArtifact = queryClient.getQueryData<ProjectArtifactResponse>(
        QUERY_KEYS.projectArtifact(id)
      )

      patchAllProjectArtifactListQueries(queryClient, (artifacts) =>
        artifacts.map((artifact) =>
          artifact.id === id
            ? {
                ...artifact,
                title: data.title ?? artifact.title,
                content: data.content ?? artifact.content,
                artifact_kind: data.artifact_kind ?? artifact.artifact_kind,
                note_type: data.note_type ?? data.artifact_kind ?? artifact.note_type,
                updated: new Date().toISOString(),
              }
            : artifact
        )
      )

      if (previousArtifact) {
        queryClient.setQueryData<ProjectArtifactResponse>(QUERY_KEYS.projectArtifact(id), {
          ...previousArtifact,
          title: data.title ?? previousArtifact.title,
          content: data.content ?? previousArtifact.content,
          artifact_kind: data.artifact_kind ?? previousArtifact.artifact_kind,
          note_type: data.note_type ?? data.artifact_kind ?? previousArtifact.note_type,
          updated: new Date().toISOString(),
        })
      }

      return { previousLists, previousArtifact }
    },
    onSuccess: (result, { id }) => {
      queryClient.setQueryData(QUERY_KEYS.projectArtifact(id), result)
      void queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.artifactReview(id),
      })
      toast({
        title: t('common.success'),
        description: t('projects.artifactUpdatedSuccess'),
      })
    },
    onError: (error: unknown, { id }, context) => {
      if (context?.previousLists) {
        restoreProjectArtifactListQueries(queryClient, context.previousLists)
      }
      if (context?.previousArtifact) {
        queryClient.setQueryData(QUERY_KEYS.projectArtifact(id), context.previousArtifact)
      }
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, t, 'projects.failedToUpdateArtifact'),
        variant: 'destructive',
      })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['projectArtifacts'] })
    },
  })
}

export function useDeleteProjectArtifact() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (id: string) => projectArtifactsApi.delete(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['projectArtifacts'] })
      const previous = snapshotProjectArtifactListQueries(queryClient)
      removeProjectArtifactFromAllQueries(queryClient, id)
      return { previous }
    },
    onSuccess: () => {
      toast({
        title: t('common.success'),
        description: t('projects.artifactDeletedSuccess'),
      })
    },
    onError: (error: unknown, _id, context) => {
      if (context?.previous) {
        restoreProjectArtifactListQueries(queryClient, context.previous)
      }
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, t, 'projects.failedToDeleteArtifact'),
        variant: 'destructive',
      })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['projectArtifacts'] })
    },
  })
}

export function useExportProjectArtifactPdf() {
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (id: string) => projectArtifactsApi.exportPdf(id),
    onSuccess: () => {
      toast({
        title: t('common.success'),
        description: t('projects.exportPdfSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, t, 'projects.failedToExportPdf'),
        variant: 'destructive',
      })
    },
  })
}
