import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import GmToolbar from '@/components/play/GmToolbar.vue'
import type { GameDetail } from '@/api/types'
import { i18n } from '@/i18n'

vi.mock('@/features/play/workbench/GmWorkspace.vue', () => ({ default: { template: '<div><slot v-for="name in [\'settings\']" :name="name" /></div>' } }))

describe('GM story mode control', () => {
  it('emits a story mode update from settings', async () => {
    const wrapper = mount(GmToolbar, {
      props: { detail: { game_key: 'g', story_mode: 'prose' } as GameDetail, players: [], isGm: true },
      global: { plugins: [i18n], stubs: { NIcon: true } },
    })
    const select = wrapper.find('[data-testid="story-mode-select"]')
    expect(select.exists()).toBe(true)
    await select.setValue('dialogue')
    expect(wrapper.emitted('story-mode')).toEqual([[{ mode: 'dialogue' }]])
  })
})
