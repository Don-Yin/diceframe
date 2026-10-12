import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import LorePerspectiveInspector from '../src/features/lorebook/LorePerspectiveInspector.vue'
import { i18n } from '../src/i18n'
import type { LorePreviewResponse } from '../src/api/types'

const preview: LorePreviewResponse = {
  ok: true,
  world_id: 'w1',
  viewer: { kind: 'gm' },
  projections: {
    a: { visible: true, audience: 'public', subjects: [] },
    b: { visible: true, audience: 'character', subjects: ['莱拉'] },
    c: { visible: false, audience: 'gm', subjects: [] },
  },
  summary: { total: 3, visible: 3, public: 1, character_only: 1, gm_secret: 1 },
}

function factory(overrides: Record<string, unknown> = {}) {
  return mount(LorePerspectiveInspector, {
    global: { plugins: [i18n] },
    props: {
      players: [{ user_id: 'u1', character_name: '莱拉' }],
      viewer: 'gm',
      viewerFallback: false,
      characterViewerLocked: false,
      lockedReason: '',
      preview,
      previewError: '',
      selectedEntry: null,
      selectedProjection: null,
      filter: 'all',
      actionText: '',
      activation: null,
      activationLoading: false,
      activationError: '',
      ...overrides,
    },
  })
}

describe('LorePerspectiveInspector', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
  })

  it('renders viewer options and emits canonical user ids', async () => {
    const wrapper = factory()
    const buttons = wrapper.findAll('.lore-viewer-options button')
    expect(buttons.map(b => b.text())).toEqual(['GM 全知', '全队', '莱拉'])

    await buttons[2].trigger('click')
    expect(wrapper.emitted('select-viewer')).toEqual([['u1']])
  })

  it('filters entries from inside the inspector', async () => {
    const wrapper = factory({ filter: 'visible' })
    const filterButtons = wrapper.findAll('.lore-filter-options button')
    expect(filterButtons.map(b => b.text())).toEqual(['全部条目', '此视角可见', '此视角未知'])
    expect(filterButtons[1].classes()).toContain('active')

    await filterButtons[2].trigger('click')
    expect(wrapper.emitted('select-filter')).toEqual([['hidden']])
  })

  it('marks the current viewer active', () => {
    const wrapper = factory({ viewer: 'party' })
    const active = wrapper.findAll('.lore-viewer-options button.active')
    expect(active).toHaveLength(1)
    expect(active[0].text()).toBe('全队')
  })

  it('disables character viewers and explains the standalone lock', () => {
    const wrapper = factory({ characterViewerLocked: true, lockedReason: 'standalone' })
    expect(wrapper.text()).toContain('未连接存档')
    const characterButton = wrapper.findAll('.lore-viewer-options button').find(b => b.text() === '莱拉')
    expect(characterButton?.attributes('disabled')).toBeDefined()
  })

  it('shows the peer lock hint in direct-connect sessions', () => {
    const wrapper = factory({ characterViewerLocked: true, lockedReason: 'peer' })
    expect(wrapper.text()).toContain('直连会话')
  })

  it('explains the fallback when the stored viewer left the game', () => {
    const wrapper = factory({ viewer: 'uX', viewerFallback: true })
    expect(wrapper.text()).toContain('已按 GM 视角显示')
  })

  it('renders the visibility summary counts', () => {
    const wrapper = factory()
    const text = wrapper.text()
    expect(text).toContain('3 / 3')
    expect(text).toContain('GM 秘密')
  })

  it('shows preview errors in the summary block', () => {
    const wrapper = factory({ preview: null, previewError: '视角无效' })
    expect(wrapper.find('.error-banner').text()).toContain('视角无效')
  })

  it('details the selected entry with badge and viewer visibility', () => {
    const wrapper = factory({
      selectedEntry: { id: 'b', name: '秘闻' },
      selectedProjection: { visible: false, audience: 'character', subjects: ['莱拉'] },
    })
    const text = wrapper.text()
    expect(text).toContain('秘闻')
    expect(text).toContain('仅莱拉可知')
    expect(text).toContain('当前视角不可见')
  })

  it('shows a hint when no entry is selected', () => {
    const wrapper = factory()
    expect(wrapper.text()).toContain('点击列表中的条目')
  })

  it('emits close when the header close button is clicked', async () => {
    const wrapper = factory()
    await wrapper.find('.lore-inspector-close').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('renders the activation trace and hides safe hidden rows for players', () => {
    const trace = [
      { entry_id: 'public', final_state: 'included', reason_code: 'matched' },
      { entry_id: '', final_state: 'hidden' },
    ]
    const gm = factory({ activation: { ok: true, trace } })
    expect(gm.find('.lore-activation-trace').text()).toContain('public')
    expect(gm.find('.lore-activation-trace').text()).toContain('hidden')

    const player = factory({ viewer: 'u1', activation: { ok: true, trace } })
    expect(player.find('.lore-activation-trace').text()).toContain('public')
    expect(player.find('.lore-activation-trace').text()).not.toContain('hidden')
  })

  it('emits the action input and activation refresh action', async () => {
    const wrapper = factory()
    await wrapper.find('.lore-activation-input').setValue('open the sealed door')
    await wrapper.find('.lore-inspector-block button').trigger('click')
    expect(wrapper.emitted('update:action-text')).toEqual([['open the sealed door']])
    expect(wrapper.emitted('refresh-activation')).toHaveLength(1)
  })
})
