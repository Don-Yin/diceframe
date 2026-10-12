import { beforeEach, describe, expect, it, vi } from 'vitest'
import { updateStateForVersion, useUpdater } from '../src/composables/useUpdater'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
}))

vi.mock('../src/api/client', () => ({
  api: mocks.api,
}))

describe('useUpdater', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mocks.api.mockReset()
    const { updateStatus, reloadCountdown } = useUpdater()
    updateStatus.value = null
    reloadCountdown.value = null
  })

  it('starts a page refresh countdown after a portable update completes', async () => {
    const updater = useUpdater()
    updater.updateStatus.value = {
      state: 'staged',
      kind: 'portable',
      current_version: '1.6.2',
      self_update: { supported: true, mode: 'portable', reason: '', hint: '' },
    }
    mocks.api
      .mockResolvedValueOnce({ ok: true, state: 'applying', version: '1.6.3' })
      .mockResolvedValueOnce({
        state: 'done',
        kind: 'portable',
        version: '1.6.3',
        current_version: '1.6.3',
        self_update: { supported: true, mode: 'portable', reason: '', hint: '' },
      })

    await updater.applyUpdate()

    expect(updater.reloadCountdown.value).toBe(5)
    await vi.advanceTimersByTimeAsync(1000)
    expect(updater.reloadCountdown.value).toBe(4)
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('does not treat a previous completed version as the newly available update', () => {
    expect(updateStateForVersion({ state: 'done', version: '1.6.3' }, 'v1.7.0')).toBe('idle')
    expect(updateStateForVersion({ state: 'done', version: 'v1.7.0' }, '1.7.0')).toBe('done')
    expect(updateStateForVersion(null, '1.7.0')).toBe('idle')
  })

  it('waits until the restarted server reports a new boot id', async () => {
    mocks.api
      .mockResolvedValueOnce({ ok: true, boot_id: 'boot-old', pid: 10, version: '1.0.0' })
      .mockResolvedValueOnce({ ok: true, boot_id: 'boot-new', pid: 11, version: '1.0.0' })

    const ready = useUpdater().waitForApplicationRestart('boot-old', 5_000)
    await vi.advanceTimersByTimeAsync(1_600)

    await expect(ready).resolves.toBe(true)
    expect(mocks.api).toHaveBeenCalledTimes(2)
    vi.clearAllTimers()
    vi.useRealTimers()
  })
})
