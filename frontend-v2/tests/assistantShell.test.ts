import { mount } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it } from 'vitest'
import AssistantShell from '../src/components/assistant/AssistantShell.vue'
import { useAssistantPreferences } from '../src/composables/useAssistantPreferences'
import { resetAssistantLauncherPosition } from '../src/composables/useAssistantLauncherPosition'
import { i18n } from '../src/i18n'

describe('DF Agent global shell', () => {
  beforeEach(() => {
    localStorage.clear()
    useAssistantPreferences().setEnabled(true)
  })

  it('defaults to visible, persists the setting, and can be disabled', async () => {
    const preferences = useAssistantPreferences()
    expect(preferences.enabled.value).toBe(true)

    preferences.setEnabled(false)
    expect(preferences.enabled.value).toBe(false)
    expect(localStorage.getItem('diceframe_assistant_enabled')).toBe('0')

    preferences.setEnabled(true)
    expect(localStorage.getItem('diceframe_assistant_enabled')).toBe('1')
  })

  it('keeps the owner entry mounted across route content and renders the home greeting only when requested', async () => {
    const wrapper = mount(AssistantShell, {
      props: { isHome: true },
      global: {
        plugins: [i18n],
        stubs: {
          NDrawer: { props: { show: Boolean }, template: '<div v-if="show" class="assistant-shell-drawer"><slot /></div>' },
          NDrawerContent: { template: '<div><slot /></div>' },
          NIcon: { template: '<span />' },
          AssistantPanel: { template: '<div data-testid="assistant-panel" />' },
        },
      },
    })

    expect(wrapper.find('[data-testid="assistant-shell-fab"]').exists()).toBe(true)
    expect(wrapper.find('.overview-assistant-bubble-wrap').exists()).toBe(true)

    await wrapper.setProps({ isHome: false })
    await nextTick()
    expect(wrapper.find('[data-testid="assistant-shell-fab"]').exists()).toBe(true)
    expect(wrapper.find('.overview-assistant-bubble-wrap').exists()).toBe(false)
  })

  it('toggles one centered expanded window without remounting the panel or losing an unsent composer draft', async () => {
    let mountCount = 0
    const PanelStub = defineComponent({
      props: { expanded: Boolean },
      emits: ['close', 'toggleExpanded'],
      setup() {
        const draft = ref('')
        mountCount += 1
        return { draft }
      },
      template: `
        <section class="assistant-panel">
          <button
            data-testid="assistant-toggle-expanded"
            :aria-label="expanded ? '缩回侧栏' : '扩大窗口'"
            :title="expanded ? '缩回侧栏' : '扩大窗口'"
            @click="$emit('toggleExpanded')"
          >toggle</button>
          <input v-model="draft" aria-label="assistant draft" />
        </section>
      `,
    })
    const wrapper = mount(AssistantShell, {
      props: { isHome: false },
      attachTo: document.body,
      global: {
        plugins: [i18n],
        stubs: {
          NDrawer: { props: { show: Boolean }, template: '<div v-if="show"><slot /></div>' },
          NDrawerContent: { template: '<div><slot /></div>' },
          'n-drawer': { props: { show: Boolean }, template: '<div v-if="show"><slot /></div>' },
          'n-drawer-content': { template: '<div><slot /></div>' },
          NIcon: { template: '<span />' },
          AssistantPanel: PanelStub,
        },
      },
    })

    await wrapper.get('[data-testid="assistant-shell-fab"]').trigger('click')
    const draft = document.body.querySelector('[aria-label="assistant draft"]') as HTMLInputElement | null
    expect(draft).not.toBeNull()
    draft!.value = '还没发送的任务草稿'
    draft!.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    const toggle = document.body.querySelector('[data-testid="assistant-toggle-expanded"]') as HTMLButtonElement | null
    expect(toggle).not.toBeNull()
    toggle!.click()
    await nextTick()

    expect(document.body.querySelector('.assistant-shell-expanded')).not.toBeNull()
    expect(mountCount).toBe(1)
    expect(document.body.querySelector('[aria-label="assistant draft"]')).toHaveProperty('value', '还没发送的任务草稿')
    expect(document.body.querySelector('[data-testid="assistant-toggle-expanded"]')?.getAttribute('aria-label')).toBe('缩回侧栏')

    const shrinkToggle = document.body.querySelector('[data-testid="assistant-toggle-expanded"]') as HTMLButtonElement
    shrinkToggle.click()
    await nextTick()
    expect(document.body.querySelector('.assistant-shell-expanded')).toBeNull()
    expect(mountCount).toBe(1)
    expect(document.body.querySelector('[aria-label="assistant draft"]')).toHaveProperty('value', '还没发送的任务草稿')
    wrapper.unmount()
  })

  it('drags the launcher without opening and persists a clamped position', async () => {
    const wrapper = mount(AssistantShell, {
      global: {
        plugins: [i18n],
        stubs: {
          NDrawer: { props: { show: Boolean }, template: '<div v-if="show" class="assistant-shell-drawer"><slot /></div>' },
          NDrawerContent: { template: '<div><slot /></div>' },
          NIcon: { template: '<span />' },
          AssistantPanel: { template: '<div data-testid="assistant-panel" />' },
        },
      },
    })
    const fab = wrapper.get('[data-testid="assistant-shell-fab"]')
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 320 })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 240 })
    Object.defineProperty(fab.element, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ left: 250, top: 170, width: 48, height: 48, right: 298, bottom: 218 }),
    })

    fab.element.dispatchEvent(new PointerEvent('pointerdown', { pointerId: 1, clientX: 260, clientY: 180, bubbles: true }))
    fab.element.dispatchEvent(new PointerEvent('pointermove', { pointerId: 1, clientX: 600, clientY: 600, bubbles: true }))
    fab.element.dispatchEvent(new PointerEvent('pointerup', { pointerId: 1, clientX: 600, clientY: 600, bubbles: true }))
    fab.element.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }))
    await nextTick()
    expect(wrapper.find('[data-testid="assistant-panel"]').exists()).toBe(false)
    expect(localStorage.getItem('diceframe_assistant_launcher_position')).toBe('{"x":272,"y":192}')
    expect((fab.element as HTMLElement).style.left).toBe('272px')
    expect((fab.element as HTMLElement).style.top).toBe('192px')

    wrapper.unmount()
  })

  it('re-clamps a persisted launcher position when the viewport shrinks', async () => {
    localStorage.setItem('diceframe_assistant_launcher_position', '{"x":500,"y":500}')
    const wrapper = mount(AssistantShell, {
      global: {
        plugins: [i18n],
        stubs: {
          NDrawer: { template: '<div><slot /></div>' },
          NDrawerContent: { template: '<div><slot /></div>' },
          NIcon: { template: '<span />' },
          AssistantPanel: true,
        },
      },
    })
    const fab = wrapper.get('[data-testid="assistant-shell-fab"]')
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 320 })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 240 })
    Object.defineProperty(fab.element, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ left: 500, top: 500, width: 48, height: 48, right: 548, bottom: 548 }),
    })
    window.dispatchEvent(new Event('resize'))
    await nextTick()
    expect((fab.element as HTMLElement).style.left).toBe('272px')
    expect((fab.element as HTMLElement).style.top).toBe('192px')
    expect(localStorage.getItem('diceframe_assistant_launcher_position')).toBe('{"x":272,"y":192}')
    wrapper.unmount()
  })

  it('ignores a delayed click from a touch drag and opens on the next deliberate tap', async () => {
    const wrapper = mount(AssistantShell, {
      global: {
        plugins: [i18n],
        stubs: {
          Drawer: { props: { show: Boolean }, template: '<div v-if="show"><slot /></div>' },
          DrawerContent: { template: '<div><slot /></div>' },
          NIcon: { template: '<span />' },
          AssistantPanel: { template: '<div data-testid="assistant-panel" />' },
        },
      },
    })
    const fab = wrapper.get('[data-testid="assistant-shell-fab"]')
    const pointer = (type: string, x: number) => fab.element.dispatchEvent(new PointerEvent(type, {
      pointerId: 3, pointerType: 'touch', clientX: x, clientY: 100, bubbles: true,
    }))
    pointer('pointerdown', 100)
    pointer('pointermove', 150)
    pointer('pointerup', 150)
    // Touch browsers can deliver the synthetic click in a later event task.
    await new Promise(resolve => setTimeout(resolve, 20))
    fab.element.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }))
    await nextTick()
    expect(wrapper.find('[data-testid="assistant-panel"]').exists()).toBe(false)
    pointer('pointerdown', 150)
    pointer('pointerup', 150)
    fab.element.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }))
    await nextTick()
    expect(wrapper.find('[data-testid="assistant-panel"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('recovers the mounted launcher and clears only its position preference', async () => {
    localStorage.setItem('diceframe_assistant_launcher_position', '{"x":50,"y":50}')
    localStorage.setItem('diceframe_assistant_messages', 'keep my conversation')
    const wrapper = mount(AssistantShell, { global: { plugins: [i18n], stubs: { Drawer: true, AssistantPanel: true } } })
    const fab = wrapper.get('[data-testid="assistant-shell-fab"]')
    expect((fab.element as HTMLElement).style.left).toBe('50px')
    resetAssistantLauncherPosition()
    await nextTick()
    expect((fab.element as HTMLElement).style.left).toBe('auto')
    expect((fab.element as HTMLElement).style.top).toBe('auto')
    expect(localStorage.getItem('diceframe_assistant_launcher_position')).toBeNull()
    expect(localStorage.getItem('diceframe_assistant_messages')).toBe('keep my conversation')
    expect(useAssistantPreferences().enabled.value).toBe(true)
    wrapper.unmount()
  })
})
