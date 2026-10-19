import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import PlayStageHeader from '../src/features/play/surface/PlayStageHeader.vue'

describe('PlayStageHeader', () => {
  it('renders a localized scene label, title, subtitle, markers, and trailing slot', () => {
    const wrapper = mount(PlayStageHeader, {
      props: { title: 'A very long scene title that must remain visible', subtitle: 'Current objective', markers: ['phase:planning', 'day:2'] },
      slots: { trailing: '<button data-testid="scene-header-action">Open history</button>' },
      global: { plugins: [i18n] },
    })

    expect(wrapper.find('.scene-strip').exists()).toBe(true)
    expect(wrapper.find('.scene-label').text()).toBe('Current scene')
    expect(wrapper.find('.scene-title').text()).toContain('A very long scene title')
    expect(wrapper.text()).toContain('Current objective')
    expect(wrapper.find('.scene-chips').text()).toContain('phase:planning')
    expect(wrapper.find('[data-testid="scene-header-action"]').exists()).toBe(true)
  })

  it('omits optional content and undefined marker values', () => {
    const wrapper = mount(PlayStageHeader, { props: { title: 'Scene', markers: [undefined, '', 'day:1'] as unknown as string[] }, global: { plugins: [i18n] } })

    expect(wrapper.find('.scene-strip').text()).not.toContain('undefined')
    expect(wrapper.find('.scene-strip').text()).not.toContain('Current objective')
    expect(wrapper.find('.scene-chips').text()).toBe('day:1')
  })

  it('keeps shared scene headers in normal flow by default', () => {
    const wrapper = mount(PlayStageHeader, { props: { title: 'Scene' }, global: { plugins: [i18n] } })
    expect(wrapper.find('.scene-strip').classes()).not.toContain('scene-strip-sticky')
    expect(wrapper.find('.scene-heading').classes()).not.toContain('scene-heading-compact')
  })

  it('exposes a compact sticky scene surface when requested by the play stage', () => {
    const wrapper = mount(PlayStageHeader, { props: { title: 'Scene', tableLayout: true }, global: { plugins: [i18n] } })
    expect(wrapper.find('.scene-strip').classes()).toContain('scene-strip-sticky')
    expect(wrapper.find('.scene-heading').classes()).toContain('scene-heading-compact')
  })
})
