import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ScriptDraft } from '../src/features/adventures/scriptTypes'

const mocks = vi.hoisted(() => ({ apiBlob: vi.fn() }))
vi.mock('../src/api/client', () => ({ apiBlob: mocks.apiBlob }))
import { organizeScript } from '../src/features/adventures/scriptAi'

function response(parts: string[]) {
  return new Response(new ReadableStream({ start(controller) {
    for (const part of parts) controller.enqueue(new TextEncoder().encode(part))
    controller.close()
  } }))
}
const draft = {} as ScriptDraft

describe('AI import progress stream', () => {
  beforeEach(() => mocks.apiBlob.mockReset())

  it('handles split network chunks and sends explicit token consent', async () => {
    mocks.apiBlob.mockResolvedValue(response(['{"type":"progress","stage":"organizing","completed":1,', '"total":3}\n{"type":"heartbeat"}\n', '{"type":"result","preview":{"ok":true,"draft":{},"blockers":[]}}\n']))
    const progress = vi.fn(), signal = new AbortController().signal
    const result = await organizeScript(draft, 'Keep secrets', 'zh-CN', signal, progress)
    expect(result.ok).toBe(true)
    expect(progress).toHaveBeenCalledWith({ stage: 'organizing', completed: 1, total: 3 })
    const [url, options] = mocks.apiBlob.mock.calls[0]
    expect(url).toBe('/adventures/script/ai?language=zh-CN')
    expect(JSON.parse(options.body)).toMatchObject({ draft, instructions: 'Keep secrets', token_consent: true })
    expect(options.signal).toBe(signal)
  })

  it('never treats a partial or failed stream as a completed draft', async () => {
    for (const body of ['{"type":"progress","stage":"validating","completed":2,"total":3}\n', '{"type":"error","error":"Invalid generated references"}\n']) {
      mocks.apiBlob.mockResolvedValue(response([body]))
      await expect(organizeScript(draft, '', 'en', new AbortController().signal, vi.fn())).rejects.toThrow()
    }
  })
})
