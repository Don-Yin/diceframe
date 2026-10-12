import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AssistantGreetingBubble from '../src/features/overview/AssistantGreetingBubble.vue'
import { i18n } from '../src/i18n'

const BUBBLE_KEY = 'overview_assistant_bubble_dismissed'

function mountBubble() {
  return mount(AssistantGreetingBubble, { global: { plugins: [i18n] } })
}

describe('AssistantGreetingBubble', () => {
  beforeEach(() => {
    localStorage.clear()
    i18n.global.locale.value = 'zh-CN'
  })

  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('greets, opens the assistant on tap, and dismisses for good', async () => {
    const wrapper = mountBubble()
    expect(wrapper.find('.overview-assistant-bubble').text()).toBe('有什么需要帮助的吗？')

    await wrapper.find('.overview-assistant-bubble').trigger('click')
    expect(wrapper.emitted('open')).toHaveLength(1)
    expect(wrapper.find('.overview-assistant-bubble-wrap').exists()).toBe(false)
    expect(localStorage.getItem(BUBBLE_KEY)).toBe('1')
  })

  it('stays hidden once dismissed', () => {
    localStorage.setItem(BUBBLE_KEY, '1')
    const wrapper = mountBubble()
    expect(wrapper.find('.overview-assistant-bubble-wrap').exists()).toBe(false)
  })

  it('dismisses via the close button and persists', async () => {
    const wrapper = mountBubble()
    await wrapper.find('.overview-assistant-bubble-close').trigger('click')
    expect(wrapper.find('.overview-assistant-bubble-wrap').exists()).toBe(false)
    expect(localStorage.getItem(BUBBLE_KEY)).toBe('1')
    expect(wrapper.emitted('open')).toBeUndefined()
  })

  it('still dismisses in-session when storage writes are rejected', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage denied')
    })
    const wrapper = mountBubble()
    await wrapper.find('.overview-assistant-bubble-close').trigger('click')
    expect(wrapper.find('.overview-assistant-bubble-wrap').exists()).toBe(false)
    // 当前 session 关闭即可；持久化失败被吞掉，不向页面抛未捕获异常
  })
})
