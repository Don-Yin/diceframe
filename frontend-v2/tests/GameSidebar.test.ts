import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { GameDetail } from '../src/api/types'
import GameSidebar from '../src/components/GameSidebar.vue'

vi.mock('../src/composables/useLocale', () => ({
  useLocale: () => ({ t: (key: string) => key }),
}))

describe('GameSidebar navigation', () => {
  it('places the map above perceptions and omits the redundant adventure entry', async () => {
    const wrapper = shallowMount(GameSidebar, {
      props: {
        detail: { state: 'paused', adventure_binding: { adventure_id: 'test:quest', version: '1.0.0' } } as GameDetail,
        privateMessages: [],
      },
    })
    const sections = wrapper.findAll('.game-sidebar > details').map(section => section.get('summary strong').text())
    expect(sections).toEqual(['mapTitle', 'characterPerception', 'statusInfo'])
    expect(wrapper.text()).not.toContain('gameAdventureBinding')
    await wrapper.get('.sidebar-map-open').trigger('click')
    expect(wrapper.emitted('open-map')).toHaveLength(1)
    wrapper.unmount()
  })
})
