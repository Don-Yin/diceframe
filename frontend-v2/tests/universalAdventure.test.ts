import { describe, expect, it } from 'vitest'
import { matchingAdventureRules } from '../src/features/library/catalogue'
import type { AdventureSummary, RuleSummary } from '../src/api/types'

const format = 'diceframe:adventure-graph-v2'
const story = { format, required_runtime: { id: 'core:adventure', minimum_version: 1 } } as AdventureSummary
const rules = [
  { rule_id: 'coc', ruleset_runtime: { id: 'core:legacy', version: 1, capabilities: { adventure_formats: [format] } } },
  { rule_id: 'custom', ruleset_runtime: { id: 'core:legacy', version: 1, capabilities: { adventure_formats: [format] } } },
  { rule_id: 'dnd', ruleset_runtime: { id: 'core:dnd2024', version: 1, capabilities: { adventure_formats: [format] } } },
  { rule_id: 'unavailable' },
] as RuleSummary[]

describe('universal story launch compatibility', () => {
  it('offers the same narrative package under CoC, custom and D&D rules', () => {
    expect(matchingAdventureRules(story, rules).map(rule => rule.rule_id)).toEqual(['coc', 'custom', 'dnd'])
  })
  it('keeps specific mechanics bound to their registered rule runtime', () => {
    expect(matchingAdventureRules({ ...story, required_runtime: { id: 'core:dnd2024', minimum_version: 1 } }, rules).map(rule => rule.rule_id)).toEqual(['dnd'])
  })
  it('rejects unsupported profile versions, formats and missing capabilities', () => {
    expect(matchingAdventureRules({ ...story, required_runtime: { id: 'core:adventure', minimum_version: 2 } }, rules)).toEqual([])
    expect(matchingAdventureRules({ ...story, format: 'diceframe:adventure-graph-v1' }, rules)).toEqual([])
    expect(matchingAdventureRules(story, [{ ...rules[0]!, ruleset_runtime: { ...rules[0]!.ruleset_runtime!, capabilities: { ...rules[0]!.ruleset_runtime!.capabilities, adventure_formats: [] } } }])).toEqual([])
  })
})
