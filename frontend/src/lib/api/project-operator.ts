import apiClient from './client'
import type {
  OperatorApprovalInbox,
  ProjectSignalStatus,
  SignalCorrectionRequest,
} from '@/lib/types/project-operator'

export const projectOperatorApi = {
  getInbox: async (projectId: string) => {
    const response = await apiClient.get<OperatorApprovalInbox>(
      `/projects/${projectId}/operator/inbox`
    )
    return response.data
  },

  detectSignals: async (projectId: string) => {
    await apiClient.post(`/projects/${projectId}/operator/signals/detect`)
  },

  updateSignalStatus: async (
    projectId: string,
    signalId: string,
    status: ProjectSignalStatus
  ) => {
    await apiClient.put(
      `/projects/${projectId}/operator/signals/${signalId}/status`,
      null,
      { params: { status } }
    )
  },

  correctSignal: async (
    projectId: string,
    signalId: string,
    correction: SignalCorrectionRequest
  ) => {
    await apiClient.post(
      `/projects/${projectId}/operator/signals/${signalId}/correction`,
      correction
    )
  },
}
