import { describe, expect, it } from 'vitest'
import { recommendedRuleSummaries } from '../src/utils/recommendedRules'
import type { RuleSummary, WorldTemplateSummary } from '../src/api/types'

const rules: RuleSummary[] = [
  { rule_id: 'freeform_fantasy', rule_name: '经典奇幻自由规则' },
  { rule_id: 'dnd5e', rule_name: 'D&D 5e Lite' },
  { rule_id: 'dnd2024_srd', rule_name: '5E 2024 SRD 高级规则' },
]

describe('recommendedRuleSummaries', () => {
  it('returns matching rules in template order', () => {
    const template: WorldTemplateSummary = {
      world_id: 'default_fantasy',
      recommended_rules: ['freeform_fantasy', 'dnd5e', 'dnd2024_srd'],
    }
    expect(recommendedRuleSummaries(template, rules).map(r => r.rule_id)).toEqual([
      'freeform_fantasy',
      'dnd5e',
      'dnd2024_srd',
    ])
  })

  it('ignores missing or duplicate recommendations', () => {
    const template: WorldTemplateSummary = { world_id: 'w', recommended_rules: ['nope', 'dnd5e', 'dnd5e', ''] }
    expect(recommendedRuleSummaries(template, rules).map(r => r.rule_id)).toEqual(['dnd5e'])
  })

  it('returns empty list when template has no recommendations', () => {
    expect(recommendedRuleSummaries({ world_id: 'w' }, rules)).toEqual([])
    expect(recommendedRuleSummaries(undefined, rules)).toEqual([])
  })
})
