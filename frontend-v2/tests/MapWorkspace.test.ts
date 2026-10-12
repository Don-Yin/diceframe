import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import MapWorkspace from '../src/components/play/MapWorkspace.vue'
import type { MapData } from '../src/api/types'

const map: MapData = {
  current_location_id: 'station',
  locations: [
    { id: 'station', name: '阿卡姆车站', content: '冒险的起点。', connected_to: ['university'], keywords: ['火车'] },
    { id: 'university', name: '密斯卡托尼克大学', content: '藏书丰富。', connected_to: ['station'] },
  ],
}

describe('MapWorkspace', () => {
  it('显示地点详情、当前位置和搜索结果', async () => {
    i18n.global.locale.value = 'zh-CN'
    const wrapper = mount(MapWorkspace, {
      global: { plugins: [i18n], stubs: { Teleport: true } },
      props: { map, currentScene: '阿卡姆车站' },
    })

    expect(wrapper.text()).toContain('冒险的起点。')
    expect(wrapper.text()).toContain('当前位置')
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('场景地图')
    await wrapper.get('input[placeholder="搜索地点或关键词"]').setValue('大学')
    expect(wrapper.get('[aria-label="地点列表"]').findAll('button')).toHaveLength(1)
    expect(wrapper.text()).toContain('密斯卡托尼克大学')
  })

  it('点击关闭按钮发出 close', async () => {
    const wrapper = mount(MapWorkspace, {
      global: { plugins: [i18n], stubs: { Teleport: true } },
      props: { map },
    })
    await wrapper.get('button[aria-label="关闭"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('shows the empty-view hint for players and the visibility hint for the GM', () => {
    i18n.global.locale.value = 'en'
    const player = mount(MapWorkspace, {
      global: { plugins: [i18n], stubs: { Teleport: true } },
      props: { map: { locations: [], visibility_hint: 'no_visible_locations' } },
    })
    expect(player.text()).toContain('No public locations yet. The GM can mark locations as visible.')

    const gm = mount(MapWorkspace, {
      global: { plugins: [i18n], stubs: { Teleport: true } },
      props: { map: { ...map, visibility_hint: 'players_see_no_locations' } },
    })
    expect(gm.text()).toContain("Players can't see any locations; set visibility in the lorebook.")

    const plain = mount(MapWorkspace, {
      global: { plugins: [i18n], stubs: { Teleport: true } },
      props: { map },
    })
    expect(plain.find('.map-visibility-hint').exists()).toBe(false)
    i18n.global.locale.value = 'zh-CN'
  })
})
