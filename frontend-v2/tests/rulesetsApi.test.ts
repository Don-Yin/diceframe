import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))

vi.mock('@/api/client', () => ({ api: apiMock }))

import {
  applyLiveCharacterAdvancement,
  applyRulesetAdvancement,
  deriveRulesetBuilderCharacter,
  fetchRulesetBuilderChoices,
  fetchRulesetExperience,
  fetchRulesetProgression,
  finalizeRulesetBuilderCharacter,
  previewLiveCharacterAdvancement,
  previewRulesetAdvancement,
  resolveLiveCharacterRest,
  resolveRulesetRest,
  validateRulesetBuilderDraft,
} from '@/api/rulesets'

describe('ruleset builder API', () => {
  beforeEach(() => apiMock.mockReset())

  it('encodes rule id and locale for experience discovery', async () => {
    apiMock.mockResolvedValue({ ok: true })

    await fetchRulesetExperience('dnd/2024', 'zh-CN')

    expect(apiMock).toHaveBeenCalledWith(
      '/rules/dnd%2F2024/experience?language=zh-CN',
    )
  })

  it.each([
    ['choices', fetchRulesetBuilderChoices],
    ['validate', validateRulesetBuilderDraft],
    ['derive', deriveRulesetBuilderCharacter],
    ['finalize', finalizeRulesetBuilderCharacter],
  ] as const)('posts the untrusted draft to %s', async (action, call) => {
    apiMock.mockResolvedValue({ ok: true })
    const draft = { name: 'Arden', nested: { value: 1 } }

    await call('dnd2024_srd', draft, 'en')

    expect(apiMock).toHaveBeenCalledWith(
      `/rules/dnd2024_srd/builder/${action}?language=en`,
      { method: 'POST', body: JSON.stringify(draft) },
    )
  })

  it('fetches one class progression with encoded query parameters', async () => {
    apiMock.mockResolvedValue({ ok: true })

    await fetchRulesetProgression('dnd/2024', 'class:wizard', 'zh-CN')

    expect(apiMock).toHaveBeenCalledWith(
      '/rules/dnd%2F2024/progression?class_ref=class%3Awizard&language=zh-CN',
    )
  })

  it.each([
    ['preview', previewRulesetAdvancement],
    ['apply', applyRulesetAdvancement],
  ] as const)('posts canonical character and choices to advancement %s', async (action, call) => {
    apiMock.mockResolvedValue({ ok: true })
    const character = { rule_binding: { runtime_id: 'core:dnd2024' } }
    const choices = { hp_method: 'fixed' }

    await call('dnd2024_srd', character, choices, 'en')

    expect(apiMock).toHaveBeenCalledWith(
      `/rules/dnd2024_srd/advancement/${action}?language=en`,
      { method: 'POST', body: JSON.stringify({ character, choices }) },
    )
  })

  it('posts rest kind and hit-die rolls to the stateless resolver', async () => {
    apiMock.mockResolvedValue({ ok: true })
    const character = { resources: { hp: 4 } }

    await resolveRulesetRest('dnd2024_srd', character, 'short', { d10: [7] })

    expect(apiMock).toHaveBeenCalledWith(
      '/rules/dnd2024_srd/rest/resolve',
      {
        method: 'POST',
        body: JSON.stringify({
          character, rest: 'short', hit_die_rolls: { d10: [7] },
        }),
      },
    )
  })

  it('uses entity paths and revisions for live advancement', async () => {
    apiMock.mockResolvedValue({ ok: true })
    const choices = { hp_method: 'fixed' }

    await previewLiveCharacterAdvancement('web|room|bot', 'player/1', choices)
    await applyLiveCharacterAdvancement('web|room|bot', 'player/1', choices, 4, 'op-5')

    expect(apiMock).toHaveBeenNthCalledWith(
      1,
      '/games/web%7Croom%7Cbot/character/player%2F1/advancement/preview',
      { method: 'POST', body: JSON.stringify({ choices }) },
    )
    expect(apiMock).toHaveBeenNthCalledWith(
      2,
      '/games/web%7Croom%7Cbot/character/player%2F1/advancement/apply',
      {
        method: 'POST',
        body: JSON.stringify({
          choices, expected_revision: 4, operation_id: 'op-5',
        }),
      },
    )
  })

  it('submits only hit-die counts to the live rest endpoint', async () => {
    apiMock.mockResolvedValue({ ok: true })

    await resolveLiveCharacterRest(
      'web|room|bot', 'gm', 'short', { d10: 1 }, 2, 'rest-3',
    )

    const [, request] = apiMock.mock.calls[0]
    expect(apiMock.mock.calls[0][0]).toBe('/games/web%7Croom%7Cbot/character/gm/rest')
    expect(JSON.parse(request.body)).toEqual({
      rest: 'short',
      hit_dice: { d10: 1 },
      confirm_elapsed_time: true,
      expected_revision: 2,
      operation_id: 'rest-3',
    })
    expect(JSON.parse(request.body)).not.toHaveProperty('hit_die_rolls')
  })
})
