import type { ReviewPlan } from '@/features/content-review/types'
export type ScriptRef = { source_kind: string; source_id: string; kind: string; id: string; digest?: string }
export type GraphNode = {
  id: string; type: string; name?: string; description?: string; chapter_id?: string | null
  visibility?: string; optional?: boolean; choice_mode?: string; transitions: Array<{ to: string; choice_id?: string; choice_label?: string; conditions?: Array<{ type: string; id?: string; key?: string; value: unknown }>; [key: string]: unknown }>
  [key: string]: unknown
}
export type ScriptFiles = Record<string, any> & {
  'manifest.json': { adventure_id: string; version: string; world_policy: string; recommended_world_id: string; [key: string]: unknown }
  'adventure.json': { id: string; name?: string; start_node_ids: string[]; chapters: Array<{ id: string; name: string; [key: string]: unknown }>; nodes: GraphNode[]; [key: string]: unknown }
}
export type ScriptDraft = { directory_id: string; files: ScriptFiles; references: ScriptRef[]; provenance?: Record<string, unknown>; warnings?: string[] }
export type ScriptPreview = {
  ok: boolean; draft: ScriptDraft; warnings: string[]; blockers: string[]; plan_digest: string
  commit_plan: ReviewPlan
}
