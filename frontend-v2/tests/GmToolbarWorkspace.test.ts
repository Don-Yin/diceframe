import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import GmToolbar from '../src/components/play/GmToolbar.vue'

describe('GM tools grouped by task', () => {
  const create = (isGm = true) => mount(GmToolbar, {
    props: { detail: { game_key: 'web|room|bot', round_number: 2, state: 'active_action' }, players: [], isGm, pendingCount: 1 },
    global: { plugins: [i18n] }, slots: { party: '<p>seat control</p>', rules: '<p>manual roll service</p>' },
  })
  it('keeps common flow controls visible and puts commands, scene and party tools in their own tabs', async () => {
    i18n.global.locale.value = 'zh-CN'
    const wrapper = create()
    const tab = (text: string) => wrapper.findAll('[role="tab"]').find(item => item.text().includes(text))!
    expect(wrapper.get('.gm-flow-group').isVisible()).toBe(true)
    expect(wrapper.get('.gm-command-group').isVisible()).toBe(false)
    await tab('设置').trigger('click')
    await wrapper.get('.gm-command-group input').setValue('hello GM')
    await tab('队伍').trigger('click')
    expect(wrapper.get('[data-section="party"]').text()).toContain('seat control')
    await tab('场景').trigger('click')
    const scene = wrapper.get('[data-section="scene"]')
    const image = scene.findAll('button').find(item => item.text().includes('冒险头图'))!
    await image.trigger('click')
    expect(wrapper.emitted('scene-image')).toHaveLength(1)
    await tab('设置').trigger('click')
    expect(wrapper.get<HTMLInputElement>('.gm-command-group input').element.value).toBe('hello GM')
    await wrapper.get('.gm-command-group button').trigger('click')
    expect(wrapper.emitted('command')).toEqual([['hello GM']])
    await tab('规则').trigger('click')
    expect(wrapper.get('[data-section="rules"]').text()).toContain('manual roll service')
  })
  it('never renders a GM workspace or its slots for a player', () => {
    const wrapper = create(false)
    expect(wrapper.find('[role="tablist"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('seat control')
  })

  it('opens each group detail by default so the grouped tools are immediately discoverable', () => {
    const wrapper = create()
    const details = wrapper.findAll('details')
    expect(details.length).toBeGreaterThan(0)
    expect(details.every(detail => (detail.element as HTMLDetailsElement).open)).toBe(true)
  })

  it('can focus a workbench group from a real pending item without remounting the tools', async () => {
    const wrapper = create()
    const command = wrapper.get('.gm-command-group input')
    await wrapper.findAll('[role="tab"]').find(item => item.text().includes('设置'))!.trigger('click')
    await command.setValue('keep this draft')
    ;(wrapper.vm as unknown as { openSection: (section: 'rules') => void }).openSection('rules')
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-section="rules"]').isVisible()).toBe(true)
    await wrapper.findAll('[role="tab"]').find(item => item.text().includes('设置'))!.trigger('click')
    expect((wrapper.get('.gm-command-group input').element as HTMLInputElement).value).toBe('keep this draft')
  })
})
