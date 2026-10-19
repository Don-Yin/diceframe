import { api, apiBlob } from './client'
import type { ReviewPlan } from '@/features/content-review/types'

export type ResourceSelector = { origin: string; key: string; kind?: string; directory?: string }
export type NativePayload = Record<string, unknown>
export type ModuleResource = { kind: string; title: string; description: string; selector: ResourceSelector }
export type ResourceSnapshot = ModuleResource & { module_id: string; payload: NativePayload; source_digest: string; fork_target: string; readonly: boolean }
export type ForkDraft = { selector: ResourceSelector; source_digest: string; package_digest: string; copy_id: string; language: string; payload: NativePayload }
export type ForkReview = { ok: boolean; draft: ForkDraft; target: string; blockers: string[]; plan_digest: string; commit_plan: ReviewPlan }
export type ForkResult = { ok: boolean; target: string; result: Record<string, unknown>; error?: string }
const root = (id: string) => `/modules/${encodeURIComponent(id)}/resources`
const post = (body: unknown) => ({ method: 'POST', body: JSON.stringify(body) })
export const resourceApi = {
  list: (id: string) => api<{ ok: boolean; resources: ModuleResource[] }>(root(id)),
  read: (id: string, selector: ResourceSelector, language: string) => api<{ ok: boolean; resource: ResourceSnapshot }>(root(id) + '/read', post({ selector, language })),
  asset: (id: string, selector: ResourceSelector) => apiBlob(root(id) + `/asset?selector=${encodeURIComponent(JSON.stringify(selector))}`),
  preview: (id: string, selector: ResourceSelector, language: string) => api<ForkReview>(root(id) + '/fork/preview', post({ selector, language })),
  review: (id: string, draft: ForkDraft) => api<ForkReview>(root(id) + '/fork/review', post(draft)),
  commit: (id: string, draft: ForkDraft, digest: string) => api<ForkResult>(root(id) + '/fork/commit', post({ ...draft, reviewed: true, plan_digest: digest })),
}
