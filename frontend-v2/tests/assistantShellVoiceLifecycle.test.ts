import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AssistantShell from '../src/components/assistant/AssistantShell.vue'
import { useAssistantPreferences } from '../src/composables/useAssistantPreferences'
import { i18n } from '../src/i18n'

const cancelListening = vi.fn()

vi.mock('../src/composables/useAssistantVoice', () => ({
  useAssistantVoice: () => ({
    listening: ref(false),
    speaking: ref(false),
    speak: vi.fn(),
    cancelListening,
  }),
}))

describe('DF Agent shell voice lifecycle', () => {
  beforeEach(() => {
    cancelListening.mockClear()
    localStorage.clear()
    useAssistantPreferences().setEnabled(true)
  })

  it('cancels voice when the mounted assistant window is closed', async () => {
    const wrapper = mount(AssistantShell, {
      global: {
        plugins: [i18n],
        stubs: {
          AssistantPanel: {
            emits: ['close'],
            template: '<button data-testid="assistant-panel-close" @click="$emit(\'close\')" />',
          },
          NIcon: { template: '<span />' },
          AssistantGreetingBubble: true,
        },
      },
    })

    await wrapper.get('[data-testid="assistant-shell-fab"]').trigger('click')
    await wrapper.get('[data-testid="assistant-panel-close"]').trigger('click')

    expect(cancelListening).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it('cancels voice when the assistant feature is disabled', async () => {
    const wrapper = mount(AssistantShell, {
      global: {
        plugins: [i18n],
        stubs: {
          AssistantPanel: { template: '<div data-testid="assistant-panel" />' },
          NIcon: { template: '<span />' },
          AssistantGreetingBubble: true,
        },
      },
    })

    await wrapper.get('[data-testid="assistant-shell-fab"]').trigger('click')
    useAssistantPreferences().setEnabled(false)
    await wrapper.vm.$nextTick()

    expect(cancelListening).toHaveBeenCalledOnce()
    wrapper.unmount()
  })
})
