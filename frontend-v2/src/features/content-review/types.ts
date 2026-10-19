export type ReviewRef = { source_kind?: string; source_id?: string; kind?: string; id?: string; digest?: string }
export type ReviewPlan = {
  drafts?: Array<{ ref: ReviewRef; payload: Record<string, unknown>; references?: ReviewRef[]; provenance?: Record<string, unknown> }>
  operations?: Array<{ action?: string; draft_ref?: ReviewRef; existing_ref?: unknown; reason?: string }>
  unresolved_references?: ReviewRef[]
  duplicate_policy?: 'update' | 'duplicate' | 'skip'
}
export const reviewRefLabel = (ref?: ReviewRef) => ref ? `${ref.source_kind || ''}:${ref.source_id || ''} / ${ref.kind || ''}:${ref.id || ''}` : ''
