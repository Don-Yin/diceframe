import { describe, expect, it, vi } from 'vitest'
import {
  installRuntimeRecovery,
  isStaleRuntimeAssetError,
  reserveRuntimeReload,
} from '@/runtimeRecovery'

function memoryStorage(): Pick<Storage, 'getItem' | 'setItem'> {
  const values = new Map<string, string>()
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value) },
  }
}

describe('runtime asset recovery', () => {
  it('recognizes lazy-module failures without treating ordinary route errors as stale builds', () => {
    expect(isStaleRuntimeAssetError(new TypeError('Failed to fetch dynamically imported module: /v2-assets/Settings-old.js'))).toBe(true)
    expect(isStaleRuntimeAssetError(new Error('permission denied'))).toBe(false)
  })

  it('allows one reload per cooldown window', () => {
    const storage = memoryStorage()
    expect(reserveRuntimeReload(storage, 1_000, 30_000)).toBe(true)
    expect(reserveRuntimeReload(storage, 5_000, 30_000)).toBe(false)
    expect(reserveRuntimeReload(storage, 31_001, 30_000)).toBe(true)
  })

  it('reloads and suppresses a stale Vite preload error once', () => {
    const reload = vi.fn()
    let routerError: ((error: unknown) => void) | undefined
    const remove = vi.fn()
    const router = {
      onError: vi.fn((handler: (error: unknown) => void) => {
        routerError = handler
        return remove
      }),
    }
    const uninstall = installRuntimeRecovery(router, {
      storage: memoryStorage(),
      now: () => 10_000,
      reload,
    })

    const event = new Event('vite:preloadError', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(reload).toHaveBeenCalledOnce()

    routerError?.(new Error('Loading chunk SettingsView failed'))
    expect(reload).toHaveBeenCalledOnce()

    uninstall()
    expect(remove).toHaveBeenCalledOnce()
  })
})
