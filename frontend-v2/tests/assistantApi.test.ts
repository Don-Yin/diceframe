import { beforeEach, describe, expect, it, vi } from 'vitest'
import { streamAssistantChat, type AssistantSource } from '../src/api/assistant'

const encoder = new TextEncoder()

function responseFromChunks(chunks: string[], status = 200): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
  return new Response(body, { status, headers: { 'Content-Type': 'text/event-stream' } })
}

describe('assistant SSE client', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('trpg_access_token', 'secret')
    vi.unstubAllGlobals()
  })

  it('parses split CRLF events, sources, deltas, and done', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(responseFromChunks([
      'event: sources\r\ndata: {"sources":[{"source":"docs/USER_GUIDE_CN.md",',
      '"heading":"API"}]}\r\n\r\ndata: {"delta":"你"}\r\n\r\n',
      'data: {"delta":"好"}\r\n\r\nevent: done\r\ndata: complete\r\n\r\n',
    ])))
    const deltas: string[] = []
    let sources: AssistantSource[] = []

    await streamAssistantChat(
      [{ role: 'user', content: 'hi' }],
      'zh-CN',
      {
        onDelta: value => deltas.push(value),
        onSources: value => { sources = value },
      },
    )

    expect(deltas.join('')).toBe('你好')
    expect(sources).toEqual([{ source: 'docs/USER_GUIDE_CN.md', heading: 'API' }])
  })

  it('surfaces SSE error events', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(responseFromChunks([
      'event: error\ndata: {"code":"LLM_NOT_CONFIGURED","error":"请先配置 API"}\n\n',
    ])))

    await expect(streamAssistantChat(
      [{ role: 'user', content: 'hi' }],
      'zh-CN',
      { onDelta: vi.fn() },
    )).rejects.toMatchObject({
      code: 'LLM_NOT_CONFIGURED',
      message: '请先配置 API',
    })
  })
})
