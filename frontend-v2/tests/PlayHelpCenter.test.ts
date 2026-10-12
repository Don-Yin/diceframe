import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

const locale = ref<'zh-CN' | 'en'>('zh-CN')
vi.mock('../src/composables/useLocale', () => ({
  useLocale: () => ({ locale }),
}))

import PlayHelpCenter from '../src/components/PlayHelpCenter.vue'

describe('play help center', () => {
  it('shows current state and D&D topics without exposing narrative actions', async () => {
    const wrapper = mount(PlayHelpCenter, {
      props: {
        isDnd: true,
        scene: '金狮酒馆',
        combatStatus: 'active',
        multiplayer: true,
        meta: { dice_system: 'd20' },
      },
    })

    expect(wrapper.text()).toContain('游玩帮助')
    expect(wrapper.text()).toContain('战斗进行中')
    expect(wrapper.text()).toContain('战斗中')
    expect(wrapper.text()).toContain('金狮酒馆')
    expect(wrapper.text()).toContain('多人协作')
    expect(wrapper.get('nav[aria-label="帮助主题"]').findAll('button')).toHaveLength(5)
    expect(wrapper.text()).not.toContain('发送行动')
  })

  it('keeps help read-only and closes through the close event', async () => {
    const wrapper = mount(PlayHelpCenter, { props: { isDnd: false } })
    const actionTab = wrapper.findAll('button').find(button => button.text() === '描述行动')
    expect(actionTab).toBeDefined()
    await actionTab!.trigger('click')
    expect(wrapper.text()).toContain('把意图说清楚')
    expect(wrapper.findAll('input, textarea, select')).toHaveLength(0)
    await wrapper.get('button[aria-label="关闭"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
