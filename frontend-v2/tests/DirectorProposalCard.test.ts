import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

const locale = ref<'zh-CN' | 'en'>('zh-CN')
vi.mock('../src/composables/useLocale', () => ({
  useLocale: () => ({ locale }),
}))

import DirectorProposalCard from '../src/components/play/DirectorProposalCard.vue'

describe('director proposal card', () => {
  it('shows a party decision and opens the campaign tool without exposing player text', async () => {
    const wrapper = mount(DirectorProposalCard, {
      props: {
        isGm: true,
        proposal: {
          kind: 'party_decision', confidence: 0.98,
          rationale: 'the active adventure step has multiple choices for a party',
          mode: 'assist', requires_gm_confirmation: true,
          action_ids: ['action:0', 'action:1'],
        },
      },
    })

    expect(wrapper.text()).toContain('需要队伍共同决定')
    expect(wrapper.text()).toContain('98%')
    expect(wrapper.text()).not.toContain('action:0')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('openCampaign')).toHaveLength(1)
  })

  it('offers the combat tool for a combat proposal', async () => {
    const wrapper = mount(DirectorProposalCard, {
      props: {
        isGm: false,
        proposal: { kind: 'combat', confidence: 0.9, mode: 'auto' },
      },
    })

    expect(wrapper.text()).toContain('剧情可能进入战斗')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('openCombat')).toHaveLength(1)
  })
})
