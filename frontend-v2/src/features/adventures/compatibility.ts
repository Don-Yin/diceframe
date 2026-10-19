import type { AdventureSummary, RuleSummary } from '@/api/types'

export const narrativeRuntimeId = 'core:adventure'
const graphV2 = 'diceframe:adventure-graph-v2'

/** Discovery advice only; the server validates format, mechanics, world and binding. */
export function adventureMatchesRule(item: AdventureSummary, rule: RuleSummary): boolean {
  const required = item.required_runtime, runtime = rule.ruleset_runtime
  if (!required?.id || !runtime || !Number.isInteger(required.minimum_version) || required.minimum_version < 1
    || !runtime.capabilities.adventure_formats?.includes(item.format)) return false
  return required.id === narrativeRuntimeId
    ? item.format === graphV2 && required.minimum_version <= 1
    : runtime.id === required.id && runtime.version >= required.minimum_version
}

export function adventureRequirementLabel(item: Pick<AdventureSummary, 'required_runtime'>, locale: string): string {
  return item.required_runtime?.id === narrativeRuntimeId
    ? (locale === 'zh-CN' ? '通用剧情' : 'Universal story')
    : item.required_runtime?.id || ''
}
