import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import GmWorkspace from '../src/features/play/workbench/GmWorkspace.vue'

describe('GM workspace navigation', () => {
  it('groups tools in five accessible tabs and preserves an unfinished draft across navigation', async () => {
    i18n.global.locale.value = 'zh-CN'
    const Draft = defineComponent({ setup: () => ({ text: ref('') }), template: '<input v-model="text" aria-label="draft" />' })
    const wrapper = mount(GmWorkspace, {
      props: { round: 3, pendingCount: 2 },
      slots: { settings: Draft, party: '<span>party tools</span>', todo: '<span>request tools</span>' },
      global: { plugins: [i18n] },
    })
    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs.map(tab => tab.text().replace(/\s+/g, ''))).toEqual(['待办2', '队伍', '场景', '规则', '设置'])
    expect(tabs[0]!.attributes('aria-selected')).toBe('true')
    expect(wrapper.get('[data-section="settings"]').isVisible()).toBe(false)
    await tabs[4]!.trigger('click')
    await wrapper.get('input').setValue('unfinished command')
    await tabs[1]!.trigger('click')
    expect(wrapper.get('[data-section="party"]').isVisible()).toBe(true)
    await tabs[4]!.trigger('click')
    expect(wrapper.get('input').element.value).toBe('unfinished command')
    expect(wrapper.findAll('input')).toHaveLength(1)
    expect(wrapper.text()).toContain('第 3 轮')
  })

  it('supports keyboard navigation and updates attention without changing the selected tool', async () => {
    i18n.global.locale.value = 'en'
    const wrapper = mount(GmWorkspace, { props: { round: 0, pendingCount: 0 }, global: { plugins: [i18n] } })
    let tabs = wrapper.findAll('[role="tab"]')
    await tabs[0]!.trigger('keydown', { key: 'End' })
    expect(tabs[4]!.attributes('aria-selected')).toBe('true')
    await tabs[4]!.trigger('keydown', { key: 'ArrowRight' })
    expect(tabs[0]!.attributes('aria-selected')).toBe('true')
    await tabs[0]!.trigger('keydown', { key: 'ArrowLeft' })
    await wrapper.setProps({ pendingCount: 4, needsAttention: true })
    tabs = wrapper.findAll('[role="tab"]')
    expect(tabs[4]!.attributes('aria-selected')).toBe('true')
    expect(tabs[0]!.text()).toContain('4')
    expect(tabs[0]!.attributes('aria-label')).toContain('attention')
    for (const tab of tabs) {
      expect(wrapper.get(`#${tab.attributes('aria-controls')}`).attributes('aria-labelledby')).toBe(tab.attributes('id'))
    }
  })

  it('keeps the workstation header and tabs sticky while its body scrolls', () => {
    const wrapper = mount(GmWorkspace, { props: { round: 1, pendingCount: 0 }, global: { plugins: [i18n] } })
    expect(wrapper.find('.gm-console-head').classes()).toContain('gm-workspace-sticky')
    expect(wrapper.find('.gm-workspace-tabs').classes()).toContain('gm-workspace-sticky')
    expect(wrapper.find('.gm-workspace-body').exists()).toBe(true)
  })
})
