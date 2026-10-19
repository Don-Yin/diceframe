import { expect, it } from 'vitest'
import { combatRollEvidence } from '../src/features/play/check-modes/combatEvidence'

it('shows authoritative candidates, chosen face and GM/rules sources in every locale', () => {
  const event = { natural: 17, rolls: [4, 17], advantage_mode: 'advantage', advantage_sources: [{ code: 'gm_grant', mode: 'advantage', reason: 'high ground' }] }
  for (const locale of ['zh-CN', 'en', 'ja', 'de', 'ru'] as const) {
    const text = combatRollEvidence(event, locale)
    expect(text).toContain('d20 [4, 17] → 17')
    expect(text).toContain('high ground')
  }
  expect(combatRollEvidence({ natural: 8 }, 'en')).toBe('d20 8')
})
