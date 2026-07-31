export type SignalSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical'
export type ProjectSignalStatus =
  | 'new'
  | 'reviewed'
  | 'dismissed'
  | 'resolved'
  | 'converted_to_action'

export interface OperatorInboxItem {
  id: string
  section: 'what_changed' | 'needs_attention' | 'recommended_actions'
  title: string
  severity: SignalSeverity
  why_it_matters: string
  recommended_action: string
  confidence: number
  evidence_ids: string[]
  affected_entity_ids: string[]
  status: ProjectSignalStatus
  created_at: string
}

export interface OperatorActivityItem {
  id: string
  event_type: string
  entity_id: string
  reason: string
  actor_type: string
  actor_id: string
  timestamp: string
}

export interface OperatorApprovalInbox {
  project_id: string
  what_changed: OperatorInboxItem[]
  needs_attention: OperatorInboxItem[]
  recommended_actions: OperatorInboxItem[]
  recent_activity: OperatorActivityItem[]
}

export interface SignalCorrectionRequest {
  corrected_summary: string
  explanation: string
  actor_id: string
}
