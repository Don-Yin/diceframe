import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { NDropdown } from 'naive-ui'
import { i18n } from '../src/i18n'
import type { Player } from '../src/api/types'
import PartyMemberMenu from '../src/features/play/surface/PartyMemberMenu.vue'

const player = { user_id: 'seat-b', character_name: 'Bea' } as Player
function mountMenu(extra = {}) {
  i18n.global.locale.value = 'zh-CN'
  return mount(PartyMemberMenu, {
    props: { player, isGm: true, currentUserId: 'seat-a', gmUid: 'seat-a', memberCount: 2, ...extra },
    global: { plugins: [i18n] },
  })
}
function keys(wrapper: ReturnType<typeof mountMenu>) {
  return wrapper.getComponent(NDropdown).props('options')!.map(option => option.key)
}

describe('party member menu', () => {
  it('groups seat operations and keeps kick after a divider at the end', () => {
    const wrapper = mountMenu()
    expect(keys(wrapper)).toEqual(['copy-link', 'edit', 'away', 'control-ai', 'danger-divider', 'kick'])
    wrapper.getComponent(NDropdown).vm.$emit('select', 'kick')
    expect(wrapper.emitted('kick')).toEqual([['seat-b']])
    wrapper.unmount()
  })

  it('labels the seat link as a claim invitation for an unclaimed character', () => {
    const wrapper = mountMenu({ player: { ...player, control: { mode: 'unclaimed' } } })
    const link = wrapper.getComponent(NDropdown).props('options')![0]
    expect(link.label).toBe('邀请认领此角色')
    expect(wrapper.get('button').attributes('aria-label')).toBe('邀请认领此角色')
    wrapper.unmount()
  })

  it('keeps the normal control-link label for a human-controlled character', () => {
    const wrapper = mountMenu({ player: { ...player, control: { mode: 'human' } } })
    const link = wrapper.getComponent(NDropdown).props('options')![0]
    expect(link.label).toBe('操作链接')
    wrapper.unmount()
  })

  it('does not offer or dispatch kick for the host, current actor or sole member', () => {
    for (const context of [{ gmUid: 'seat-b' }, { currentUserId: 'seat-b' }, { memberCount: 1 }]) {
      const wrapper = mountMenu(context)
      expect(keys(wrapper)).not.toContain('kick')
      wrapper.getComponent(NDropdown).vm.$emit('select', 'kick')
      expect(wrapper.emitted('kick')).toBeUndefined()
      if ('currentUserId' in context) expect(keys(wrapper)).not.toContain('away')
      wrapper.unmount()
    }
  })

  it('preserves temporary AI hosting and the return action', () => {
    const wrapper = mountMenu({ player: { ...player, control: { mode: 'ai', temporary: true } }, away: true })
    expect(keys(wrapper)).not.toContain('control-human')
    expect(keys(wrapper)).not.toContain('control-ai')
    wrapper.getComponent(NDropdown).vm.$emit('select', 'away')
    expect(wrapper.emitted('set-away')).toEqual([['seat-b', false]])
    wrapper.unmount()
    const permanent = mountMenu({ player: { ...player, control: { mode: 'ai' } } })
    expect(keys(permanent)).toContain('control-human')
    permanent.getComponent(NDropdown).vm.$emit('select', 'control-human')
    expect(permanent.emitted('set-control')).toEqual([['seat-b', 'human']])
    permanent.unmount()
  })

  it('blocks operations while busy or after GM access is removed', async () => {
    const wrapper = mountMenu()
    const dropdown = wrapper.getComponent(NDropdown)
    await wrapper.setProps({ busy: true })
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    dropdown.vm.$emit('select', 'copy-link')
    expect(wrapper.emitted('copy-link')).toBeUndefined()
    await wrapper.setProps({ busy: false, isGm: false })
    expect(wrapper.find('button').exists()).toBe(false)
    dropdown.vm.$emit('select', 'kick')
    expect(wrapper.emitted('kick')).toBeUndefined()
    wrapper.unmount()
  })
})
