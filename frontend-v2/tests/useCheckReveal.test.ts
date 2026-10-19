import { defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { useCheckReveal } from '../src/features/play/check-decisions/useCheckReveal'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

function setup() {
  let gameKey = 'web|room|bot'
  let runId = 'run-1'
  let viewer = 'p1'
  const api = vi.fn()
  const applyRecord = vi.fn()
  const refresh = vi.fn(async () => {})
  const reportError = vi.fn()
  const reveal = useCheckReveal({
    api,
    gameKey: () => gameKey,
    runId: () => runId,
    viewer: () => viewer,
    applyRecord,
    refresh,
    reportError,
  })
  return { reveal: reveal.reveal, busyIds: reveal.busyIds, api, applyRecord, refresh, reportError, setGame: (value: string) => { gameKey = value }, setRun: (value: string) => { runId = value }, setViewer: (value: string) => { viewer = value } }
}

describe('useCheckReveal', () => {
  it('deduplicates an in-flight request for the same check', async () => {
    const ctx = setup()
    const response = deferred<{ ok: true; check_id: string; reveal: { by: string; at: string } }>()
    ctx.api.mockReturnValue(response.promise)
    const first = ctx.reveal('check-1')
    const second = ctx.reveal('check-1')
    expect(ctx.api).toHaveBeenCalledTimes(1)
    expect(ctx.busyIds.value).toEqual(['check-1'])
    response.resolve({ ok: true, check_id: 'check-1', reveal: { by: 'p1', at: 'now' } })
    await Promise.all([first, second])
    expect(ctx.applyRecord).toHaveBeenCalledWith('check-1', { by: 'p1', at: 'now' })
    expect(ctx.refresh).toHaveBeenCalledTimes(1)
  })

  it('does not write a response after run or viewer context changes', async () => {
    const ctx = setup()
    const response = deferred<{ ok: true; check_id: string; reveal: { by: string; at: string } }>()
    ctx.api.mockReturnValue(response.promise)
    const pending = ctx.reveal('check-2')
    ctx.setRun('run-2')
    ctx.setViewer('p2')
    response.resolve({ ok: true, check_id: 'check-2', reveal: { by: 'p1', at: 'now' } })
    await pending
    expect(ctx.applyRecord).not.toHaveBeenCalled()
    expect(ctx.refresh).not.toHaveBeenCalled()
  })

  it.each([
    ['game', (ctx: ReturnType<typeof setup>) => ctx.setGame('web|other|bot')],
    ['run', (ctx: ReturnType<typeof setup>) => ctx.setRun('run-2')],
    ['viewer', (ctx: ReturnType<typeof setup>) => ctx.setViewer('p2')],
  ])('fences a response after only the %s changes', async (_name, change) => {
    const ctx = setup()
    const response = deferred<{ ok: true; check_id: string; reveal: { by: string; at: string } }>()
    ctx.api.mockReturnValue(response.promise)
    const pending = ctx.reveal('check-3')
    change(ctx)
    response.resolve({ ok: true, check_id: 'check-3', reveal: { by: 'p1', at: 'now' } })
    await pending
    expect(ctx.applyRecord).not.toHaveBeenCalled()
    expect(ctx.refresh).not.toHaveBeenCalled()
  })

  it('reports an error, clears busy state, and permits retry', async () => {
    const ctx = setup()
    ctx.api.mockResolvedValueOnce({ ok: false, error: 'stale' })
      .mockResolvedValueOnce({ ok: true, check_id: 'check-4', reveal: { by: 'p1', at: 'now' } })
    await ctx.reveal('check-4')
    expect(ctx.reportError).toHaveBeenCalledTimes(1)
    await ctx.reveal('check-4')
    expect(ctx.applyRecord).toHaveBeenCalledTimes(1)
  })

  it('keeps pending buttons scoped to the current game even when check IDs coincide', async () => {
    const gameKey = ref('web|first|bot')
    const response = deferred<{ ok: true; reveal: { by: string; at: string } }>()
    const ctx = useCheckReveal({ api: vi.fn(() => response.promise),
      gameKey: () => gameKey.value, runId: () => 'run', viewer: () => 'gm',
      applyRecord: vi.fn(), refresh: vi.fn(async () => {}), reportError: vi.fn() })
    const first = ctx.reveal('same-check')
    expect(ctx.busyIds.value).toEqual(['same-check'])
    gameKey.value = 'web|second|bot'
    expect(ctx.busyIds.value).toEqual([])
    response.resolve({ ok: true, reveal: { by: 'gm', at: 'now' } })
    await first
  })

  it('permits retry after the request dependency throws synchronously', async () => {
    const ctx = setup()
    ctx.api.mockImplementationOnce(() => { throw new Error('connection unavailable') })
      .mockResolvedValueOnce({ ok: true, reveal: { by: 'p1', at: 'now' } })
    await ctx.reveal('retry-check')
    expect(ctx.busyIds.value).toEqual([])
    await ctx.reveal('retry-check')
    expect(ctx.api).toHaveBeenCalledTimes(2)
    expect(ctx.applyRecord).toHaveBeenCalledTimes(1)
  })

  it('does not write or report after its scope is disposed', async () => {
    const response = deferred<{ ok: true; check_id: string; reveal: { by: string; at: string } }>()
    const applyRecord = vi.fn()
    const reportError = vi.fn()
    let ctx!: ReturnType<typeof useCheckReveal>
    const wrapper = mount(defineComponent({ setup() {
      ctx = useCheckReveal({
        api: vi.fn(() => response.promise),
        gameKey: () => 'web|room|bot', runId: () => 'run-1', viewer: () => 'p1',
        applyRecord, refresh: vi.fn(async () => {}), reportError,
      })
      return () => null
    } }))
    const pending = ctx.reveal('check-5')
    wrapper.unmount()
    response.resolve({ ok: true, check_id: 'check-5', reveal: { by: 'p1', at: 'now' } })
    await pending
    await flushPromises()
    expect(applyRecord).not.toHaveBeenCalled()
    expect(reportError).not.toHaveBeenCalled()
    expect(ctx.busyIds.value).toEqual([])
  })
})
