import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authorizeAssistantAgent, cancelAssistantAgent, confirmAssistantAgent, getAssistantAgentCapabilities, getAssistantAgentSession, resumeAssistantAgent, reviewAssistantAgent, streamAssistantAgent, streamAssistantChat, type AssistantSource } from '../src/api/assistant'

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

  it('sends an agent run and dispatches agent events', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(responseFromChunks([
      'event: session\ndata: {"session_id":"s-1"}\n\n',
      'event: status\ndata: {"message":"planning"}\n\n',
      'event: tool_start\ndata: {"tool":"create","label":"Create"}\n\n',
      'data: {"delta":"ok"}\n\n',
      'event: done\ndata: complete\n\n',
    ])))
    const events: Array<[string, Record<string, unknown>]> = []
    const deltas: string[] = []

    await streamAssistantAgent(
      [{ role: 'user', content: 'create' }],
      'en',
      {
        onDelta: value => deltas.push(value),
        onAgentEvent: (event, payload) => events.push([event, payload]),
      },
      undefined,
      's-0',
      { route: 'create', game_key: 'g-1' },
    )

    expect(fetch).toHaveBeenCalledWith('/api/assistant/agent/run', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        messages: [{ role: 'user', content: 'create' }],
        language: 'en',
        session_id: 's-0',
        context: { route: 'create', game_key: 'g-1' },
      }),
    }))
    expect(deltas).toEqual(['ok'])
    expect(events.map(([event]) => event)).toEqual(['session', 'status', 'tool_start'])
  })

  it('calls agent confirm, review, and session endpoints', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/confirm')) return new Response(JSON.stringify({ ok: true, result: 'done' }), { status: 200 })
      if (url.endsWith('/review')) return new Response(JSON.stringify({ ok: true, draft_id: 'd-1', review: { ok: true } }), { status: 200 })
      return new Response(JSON.stringify({ ok: true, session_id: 's-1', pending: null, drafts: {}, receipts: [], status: 'idle' }), { status: 200 })
    }))

    await expect(confirmAssistantAgent('s-1', 'a-1', 'digest', true)).resolves.toMatchObject({ ok: true })
    await expect(reviewAssistantAgent('s-1', 'd-1', { name: 'x' })).resolves.toMatchObject({ draft_id: 'd-1' })
    await expect(getAssistantAgentSession('s-1')).resolves.toMatchObject({ session_id: 's-1' })
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('resumes a prepared plan through the dedicated endpoint', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true, partial: true, pending: null }), { status: 200 })))

    await expect(resumeAssistantAgent('s-1', 'a-1', 'sha256:digest')).resolves.toMatchObject({ partial: true })
    expect(fetch).toHaveBeenCalledWith('/api/assistant/agent/resume', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ session_id: 's-1', approval_id: 'a-1', plan_digest: 'sha256:digest' }),
    }))
  })

  it('uses server authorization and capability contracts', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/capabilities')) return new Response(JSON.stringify({ ok: true, revision: 'r1', capabilities: [] }), { status: 200 })
      if (url.includes('/cancel')) return new Response(JSON.stringify({ ok: true, cancelled: true }), { status: 200 })
      return new Response(JSON.stringify({ ok: true, session_id: 's-1', authorization: { mode: 'task', scope: {}, domains: [], expires_at: 1, max_steps: 32, remaining_steps: 32 } }), { status: 200 })
    }))
    await expect(getAssistantAgentCapabilities({ q: 'book', domain: 'lorebook' })).resolves.toMatchObject({ revision: 'r1' })
    await expect(authorizeAssistantAgent({ session_id: 's-1', mode: 'task', max_steps: 99 })).resolves.toMatchObject({ session_id: 's-1' })
    await expect(cancelAssistantAgent('s-1')).resolves.toMatchObject({ cancelled: true })
    expect(fetch).toHaveBeenCalledWith('/api/assistant/agent/capabilities?q=book&domain=lorebook', expect.anything())
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls[1][1].body).toContain('"max_steps":64')
  })
})
