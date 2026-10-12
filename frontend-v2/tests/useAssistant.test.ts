import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  stream: vi.fn(),
}))

vi.mock('../src/api/assistant', () => ({
  streamAssistantChat: mocks.stream,
}))

import { useAssistant } from '../src/composables/useAssistant'

describe('useAssistant request history', () => {
  beforeEach(() => {
    mocks.stream.mockReset()
    mocks.stream.mockResolvedValue(undefined)
    localStorage.clear()
    useAssistant().clear()
  })

  it('sends a non-empty user message as the final request item', async () => {
    const assistant = useAssistant()
    await assistant.send('  怎么配置模型接口？  ', 'zh-CN')

    const history = mocks.stream.mock.calls[0][0]
    expect(history).toEqual([{ role: 'user', content: '怎么配置模型接口？' }])
    expect(history.at(-1)).toMatchObject({ role: 'user' })
  })

  it('drops an empty assistant placeholder left by an earlier failed request', async () => {
    mocks.stream.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(undefined)
    const assistant = useAssistant()

    await assistant.send('第一个问题', 'zh-CN')
    await assistant.send('第二个问题', 'zh-CN')

    const secondHistory = mocks.stream.mock.calls[1][0]
    expect(secondHistory).toEqual([
      { role: 'user', content: '第一个问题' },
      { role: 'user', content: '第二个问题' },
    ])
    expect(secondHistory.at(-1)).toEqual({ role: 'user', content: '第二个问题' })
  })
})
