import { ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AssistantPanel from '../src/components/AssistantPanel.vue'

const send = vi.fn().mockResolvedValue(undefined)

vi.mock('@/composables/useLocale', () => ({
  useLocale: () => ({
    locale: ref('zh-CN'),
    t: (key: string) => `translated:${key}`,
  }),
}))

vi.mock('@/composables/useAssistant', () => ({
  useAssistant: () => ({
    messages: ref([]),
    streaming: ref(false),
    send,
    stop: vi.fn(),
    retryLast: vi.fn(),
    clear: vi.fn(),
  }),
}))

describe('DF Assistant runtime log entry', () => {
  beforeEach(() => send.mockClear())

  it('submits the runtime-log diagnostic action through the normal assistant request flow', async () => {
    const wrapper = mount(AssistantPanel)

    await wrapper.get('[data-assistant-intent="runtime-logs"]').trigger('click')

    expect(send).toHaveBeenCalledOnce()
    expect(send).toHaveBeenCalledWith(expect.any(String), 'zh-CN')
  })
})
