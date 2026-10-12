import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import KpQuestionDialog from '../src/components/play/KpQuestionDialog.vue'
import { api } from '../src/api/client'

vi.mock('../src/api/client', () => {
  class ApiError extends Error {
    constructor(message: string, public status: number, public code?: string, public retryAfter?: number) { super(message) }
  }
  return { api: vi.fn(), apiBlob: vi.fn(), ApiError }
})

const mockedApi = vi.mocked(api)

function buttonByText(wrapper: ReturnType<typeof mount>, text: string) {
  const button = wrapper.findAll('button').find(candidate => candidate.text() === text)
  if (!button) throw new Error(`未找到按钮：${text}`)
  return button
}

describe('KpQuestionDialog', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    mockedApi.mockReset()
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('submits only a question and renders the private read-only answer', async () => {
    mockedApi.mockResolvedValue({
      ok: true,
      kind: 'kp_table_talk',
      answer: '你曾在学院的旧手稿中见过相似符号。',
      advanced: false,
      action_consumed: false,
      round_number: 3,
      visibility: 'private',
    })
    const wrapper = mount(KpQuestionDialog, {
      attachTo: document.body,
      global: { plugins: [i18n], stubs: { Teleport: true } },
      props: { gameKey: 'web|room|bot' },
    })

    await wrapper.get('textarea').setValue('我认识这个符号吗？')
    await buttonByText(wrapper, '询问').trigger('click')
    await flushPromises()

    expect(mockedApi).toHaveBeenCalledWith('/games/web%7Croom%7Cbot/kp-question', {
      method: 'POST',
      body: JSON.stringify({ question: '我认识这个符号吗？', visibility: 'private' }),
    })
    expect(document.body.textContent).toContain('你曾在学院的旧手稿中见过相似符号。')
    expect(wrapper.emitted('close')).toBeUndefined()
    wrapper.unmount()
  })

  it('explicitly asks with party-safe visibility and emits a refresh signal', async () => {
    mockedApi.mockResolvedValue({
      ok: true, kind: 'kp_table_talk', answer: '全队都见过这个标志。',
      advanced: false, action_consumed: false, round_number: 3, visibility: 'party',
    })
    const wrapper = mount(KpQuestionDialog, {
      attachTo: document.body,
      global: { plugins: [i18n], stubs: { Teleport: true } },
      props: { gameKey: 'web|room|bot' },
    })

    await wrapper.get('textarea').setValue('大家都认识这个标志吗？')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await buttonByText(wrapper, '询问').trigger('click')
    await flushPromises()

    expect(JSON.parse(String(mockedApi.mock.calls[0]?.[1]?.body))).toEqual({
      question: '大家都认识这个标志吗？', visibility: 'party',
    })
    expect(wrapper.emitted('shared')).toHaveLength(1)
    wrapper.unmount()
  })
})
