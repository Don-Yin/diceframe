import { DOMWrapper, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PlayUtilityMenu from '../src/features/play/surface/PlayUtilityMenu.vue'

describe('play utility access', () => {
  afterEach(() => { document.body.innerHTML = '' })
  const panel = () => new DOMWrapper(document.querySelector<HTMLElement>('[data-testid="play-tools-panel"]')!)

  it('keeps tools discoverable and returns keyboard focus on Escape', async () => {
    const wrapper = mount(PlayUtilityMenu, { props: { label: 'Table tools' }, slots: { default: '<button>Gallery</button><button>Refresh</button>' }, attachTo: document.body })
    const trigger = wrapper.get('[data-testid="play-tools-toggle"]')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(document.activeElement?.textContent).toBe('Gallery')
    await panel().trigger('keydown', { key: 'Escape' })
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })

  it('closes after a tool action without intercepting it or stealing its dialog focus', async () => {
    const action = vi.fn()
    const wrapper = mount(PlayUtilityMenu, { props: { label: 'Tools' }, slots: { default: '<button>Gallery</button>' }, attachTo: document.body })
    await wrapper.get('[data-testid="play-tools-toggle"]').trigger('click')
    panel().get('button').element.addEventListener('click', action)
    await panel().get('button').trigger('click')
    expect(action).toHaveBeenCalledOnce()
    expect(wrapper.get('[data-testid="play-tools-toggle"]').attributes('aria-expanded')).toBe('false')
    wrapper.unmount()
  })

  it('dismisses outside the tools without hiding a tool merely on internal pointer interaction', async () => {
    const wrapper = mount(PlayUtilityMenu, { props: { label: 'Tools' }, slots: { default: '<button>Map</button>' }, attachTo: document.body })
    await wrapper.get('[data-testid="play-tools-toggle"]').trigger('click')
    await panel().trigger('pointerdown')
    expect(wrapper.get('[data-testid="play-tools-toggle"]').attributes('aria-expanded')).toBe('true')
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-testid="play-tools-toggle"]').attributes('aria-expanded')).toBe('false')
    wrapper.unmount()
  })

  it('focuses a visible tool instead of scrolling a hidden tool into view', async () => {
    const wrapper = mount(PlayUtilityMenu, { props: { label: 'Tools' }, slots: { default: '<button style="display:none">Hidden</button><button>Map</button>' }, attachTo: document.body })
    await wrapper.get('[data-testid="play-tools-toggle"]').trigger('click')
    expect(document.activeElement?.textContent).toBe('Map')
    wrapper.unmount()
  })
})
