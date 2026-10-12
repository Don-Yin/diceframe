import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const submit = vi.hoisted(() => vi.fn())
vi.mock('../src/api/rulesets', () => ({ submitRulesetIntent: submit }))
vi.mock('../src/composables/useLocale', () => ({
  useLocale: () => ({ locale: ref('zh-CN') }),
}))

import CombatMessageComposer from '../src/components/play/CombatMessageComposer.vue'

describe('combat message composer', () => {
  beforeEach(() => submit.mockReset().mockResolvedValue({ ok: true }))

  it('sends non-mechanical combat communication as a canonical intent', async () => {
    const wrapper = mount(CombatMessageComposer, {
      props: {
        gameKey: 'web|combat|bot',
        gameplay: { state_version: 7 } as any,
      },
    })
    await wrapper.get('textarea').setValue('我来挡住它！')
    await wrapper.findAll('button').find(button => button.text().includes('发送发言'))!.trigger('click')
    await flushPromises()

    expect(submit).toHaveBeenCalledOnce()
    expect(submit.mock.calls[0][1]).toMatchObject({
      type: 'combat.message', expected_version: 7, text: '我来挡住它！',
    })
    expect(submit.mock.calls[0][1]).not.toHaveProperty('actor_id')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.text()).toContain('不会消耗动作或推进回合')
  })
})
