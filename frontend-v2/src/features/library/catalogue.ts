import type { AdventureSummary, RuleSummary } from '@/api/types'
import type { RouteLocationRaw } from 'vue-router'
import { adventureMatchesRule } from '@/features/adventures/compatibility'

// Discovery has no selected world or ruleset. Use the advertised runtime
// capabilities here; CreateView and the server still validate the final binding.
export function matchingAdventureRules(item: AdventureSummary, rules: RuleSummary[]): RuleSummary[] {
  return rules.filter(rule => adventureMatchesRule(item, rule))
}

export function adventureLaunchTarget(item: AdventureSummary): RouteLocationRaw | null {
  if (!item.adventure_id || (item.source_kind === 'plugin' && !item.source_id)) return null
  return { name: 'create', query: {
    adventure_id: item.adventure_id,
    return_to: 'library',
    ...(item.source_kind === 'plugin' ? { module_id: item.source_id } : {}),
  } }
}
