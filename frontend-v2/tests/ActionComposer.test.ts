import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import ActionComposer from '../src/components/ActionComposer.vue'
import { api } from '../src/api/client'
import type { GameDetail } from '../src/api/types'

vi.mock('../src/api/client', () => {
  class ApiError extends Error {
    constructor(message: string, public status: number, public code?: string, public retryAfter?: number) { super(message) }
  }
  return { api: vi.fn(), apiBlob: vi.fn(), ApiError }
})

const mockedApi = vi.mocked(api)

function detail(submitted = true, roundNumber = 3): GameDetail {
  return {
    game_key: 'web|room|bot',
    round_number: roundNumber,
    solo_mode: false,
    multiplayer: {
      submitted_actions: submitted
        ? [{ user_id: 'player-1', text: '检查门锁', revision_count: 1 }]
        : [],
    },
  }
}

describe('ActionComposer rollback refresh', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    mockedApi.mockReset()
  })

  function actionButton(wrapper: ReturnType<typeof mount>) {
    const button = wrapper.findAll('button').find(candidate => candidate.text() === '行动')
    if (!button) throw new Error('未找到行动按钮')
    return button
  }

  it('never restores the removed player-side dice gate, including old phase responses', async () => {
    mockedApi.mockResolvedValue({ phase: 'dice', message: '需要掷骰' })
    const wrapper = mount(ActionComposer, {
      global: { plugins: [i18n] },
      props: {
        gameKey: 'web|room|bot',
        userId: 'player-1',
        detail: detail(false),
      },
    })

    await wrapper.get('textarea').setValue('检查门锁')
    await actionButton(wrapper).trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('需要掷骰')
    expect(wrapper.text()).toContain('行动已记录')

    await wrapper.setProps({ detail: detail(true) })
    await wrapper.setProps({ detail: detail(false) })

    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('行动已记录')
  })

  it('clears stale submission feedback when the round moves backward', async () => {
    mockedApi.mockResolvedValue({})
    const wrapper = mount(ActionComposer, {
      global: { plugins: [i18n] },
      props: {
        gameKey: 'web|room|bot',
        userId: 'player-1',
        detail: detail(false, 4),
      },
    })

    await wrapper.get('textarea').setValue('观察走廊')
    await actionButton(wrapper).trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('行动已记录')

    await wrapper.setProps({ detail: detail(false, 3) })

    expect(wrapper.text()).not.toContain('行动已记录')
    expect(wrapper.find('textarea').exists()).toBe(true)
  })

  it('submits only the natural-language action and leaves checks to the server', async () => {
    mockedApi.mockResolvedValueOnce({ phase: 'done', advanced: true })
    const wrapper = mount(ActionComposer, {
      global: { plugins: [i18n] },
      props: {
        gameKey: 'web|room|bot',
        userId: 'player-1',
        detail: detail(false),
      },
    })

    await wrapper.get('textarea').setValue('悄悄上楼')
    await actionButton(wrapper).trigger('click')
    await flushPromises()
    const request = mockedApi.mock.calls[0]?.[1] as { body?: string }
    expect(JSON.parse(request.body || '{}')).toEqual({ text: '悄悄上楼' })
  })

})
