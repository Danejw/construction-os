import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { projectOperatorApi } from '@/lib/api/project-operator'
import type {
  ProjectSignalStatus,
  SignalCorrectionRequest,
} from '@/lib/types/project-operator'

const inboxKey = (projectId: string) => ['project-operator', projectId, 'inbox'] as const

export function useProjectOperatorInbox(projectId: string) {
  return useQuery({
    queryKey: inboxKey(projectId),
    queryFn: () => projectOperatorApi.getInbox(projectId),
    enabled: Boolean(projectId),
  })
}

export function useDetectProjectSignals(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => projectOperatorApi.detectSignals(projectId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: inboxKey(projectId) }),
  })
}

export function useUpdateProjectSignalStatus(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      signalId,
      status,
    }: {
      signalId: string
      status: ProjectSignalStatus
    }) => projectOperatorApi.updateSignalStatus(projectId, signalId, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: inboxKey(projectId) }),
  })
}

export function useCorrectProjectSignal(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      signalId,
      correction,
    }: {
      signalId: string
      correction: SignalCorrectionRequest
    }) => projectOperatorApi.correctSignal(projectId, signalId, correction),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: inboxKey(projectId) }),
  })
}
