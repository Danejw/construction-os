import type {
  ArtifactReviewClaimFinding,
  ArtifactReviewFindingsReport,
  ArtifactReviewMemoryFinding,
  ArtifactReviewMemoryVerdict,
  ArtifactReviewSourceVerdict,
} from '@/lib/types/api'

const SOURCE_VERDICTS = new Set<ArtifactReviewSourceVerdict>([
  'supported',
  'unsupported',
  'contradicted',
  'not_in_corpus',
  'opinion',
])

const MEMORY_VERDICTS = new Set<ArtifactReviewMemoryVerdict>([
  'memory_aligned',
  'memory_conflict',
  'memory_novel',
])

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function asOptionalString(value: unknown): string | null | undefined {
  if (value === undefined) return undefined
  if (value === null) return null
  if (typeof value === 'string') return value
  return undefined
}

function parseClaimFinding(value: unknown): ArtifactReviewClaimFinding | null {
  const row = asRecord(value)
  if (!row) return null
  const findingId = row.finding_id
  const claimText = row.claim_text
  const sourceVerdict = row.source_verdict
  if (typeof findingId !== 'string' || typeof claimText !== 'string') {
    return null
  }
  if (
    typeof sourceVerdict !== 'string' ||
    !SOURCE_VERDICTS.has(sourceVerdict as ArtifactReviewSourceVerdict)
  ) {
    return null
  }
  return {
    finding_id: findingId,
    claim_text: claimText,
    source_verdict: sourceVerdict as ArtifactReviewSourceVerdict,
    confidence: typeof row.confidence === 'number' ? row.confidence : undefined,
    evidence_ids: Array.isArray(row.evidence_ids)
      ? row.evidence_ids.filter((id): id is string => typeof id === 'string')
      : undefined,
    rationale: typeof row.rationale === 'string' ? row.rationale : undefined,
    suggested_fix: asOptionalString(row.suggested_fix),
    claim_span: asOptionalString(row.claim_span),
  }
}

function parseMemoryFinding(value: unknown): ArtifactReviewMemoryFinding | null {
  const row = asRecord(value)
  if (!row) return null
  const findingId = row.finding_id
  const memoryVerdict = row.memory_verdict
  if (typeof findingId !== 'string') return null
  if (
    typeof memoryVerdict !== 'string' ||
    !MEMORY_VERDICTS.has(memoryVerdict as ArtifactReviewMemoryVerdict)
  ) {
    return null
  }
  return {
    finding_id: findingId,
    claim_text: asOptionalString(row.claim_text),
    memory_verdict: memoryVerdict as ArtifactReviewMemoryVerdict,
    fact_id: asOptionalString(row.fact_id),
    rationale: typeof row.rationale === 'string' ? row.rationale : undefined,
    suggested_fix: asOptionalString(row.suggested_fix),
  }
}

/** Parse persisted review findings into typed claim/memory arrays. */
export function parseArtifactReviewFindings(
  findings: unknown
): ArtifactReviewFindingsReport {
  const root = asRecord(findings)
  if (!root) {
    return { claims: [], memory_findings: [] }
  }
  const claimsRaw = Array.isArray(root.claims) ? root.claims : []
  const memoryRaw = Array.isArray(root.memory_findings)
    ? root.memory_findings
    : []
  return {
    claims: claimsRaw
      .map(parseClaimFinding)
      .filter((item): item is ArtifactReviewClaimFinding => item !== null),
    memory_findings: memoryRaw
      .map(parseMemoryFinding)
      .filter((item): item is ArtifactReviewMemoryFinding => item !== null),
    truncated: typeof root.truncated === 'boolean' ? root.truncated : undefined,
    notes: asOptionalString(root.notes),
  }
}

export function findingHasSuggestedFix(
  finding: Pick<ArtifactReviewClaimFinding, 'suggested_fix'>
): boolean {
  return Boolean(finding.suggested_fix?.trim())
}
