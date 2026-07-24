import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { projectArtifactsApi } from '@/lib/api/project-artifacts'
import { QUERY_KEYS } from '@/lib/api/query-client'
import {
  ArtifactReviewApplyRequest,
  ArtifactReviewRunResponse,
} from '@/lib/types/api'

export interface UseArtifactReviewOptions {
  enabled?: boolean
  pollWhileRunning?: boolean
}

async function fetchLatestReview(
  noteId: string
): Promise<ArtifactReviewRunResponse | null> {
  try {
    return await projectArtifactsApi.getLatestReview(noteId)
  } catch (error: unknown) {
    // 404 = no review run yet — treat as empty data, not an error
    if (isAxiosError(error) && error.response?.status === 404) {
      return null
    }
    throw error
  }
}

export function useArtifactReview(
  noteId: string | undefined,
  options: UseArtifactReviewOptions = {}
) {
  const { enabled = true, pollWhileRunning = true } = options

  return useQuery({
    queryKey: QUERY_KEYS.artifactReview(noteId || ''),
    queryFn: () => fetchLatestReview(noteId!),
    enabled: Boolean(noteId) && enabled,
    refetchInterval: (query) => {
      if (!pollWhileRunning) {
        return false
      }
      const status = query.state.data?.status
      return status === 'pending' || status === 'running' ? 2000 : false
    },
    retry: (count, error) => {
      if (isAxiosError(error) && error.response?.status === 404) {
        return false
      }
      return count < 2
    },
  })
}

export function useStartArtifactReview() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (noteId: string) => projectArtifactsApi.startReview(noteId),
    onSuccess: (_data, noteId) => {
      void queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.artifactReview(noteId),
      })
    },
  })
}

export function useApplyArtifactReviewFixes() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      noteId,
      data,
    }: {
      noteId: string
      data: ArtifactReviewApplyRequest
    }) => projectArtifactsApi.applyReviewFixes(noteId, data),
    onSuccess: (result, { noteId }) => {
      queryClient.setQueryData(QUERY_KEYS.projectArtifact(noteId), result.artifact)
      void queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.artifactReview(noteId),
      })
      void queryClient.invalidateQueries({ queryKey: ['projectArtifacts'] })
    },
  })
}
