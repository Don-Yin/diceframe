import { describe, expect, it } from 'vitest'
import { shouldAutoDownloadUpdate } from '../src/composables/useUpdater'

describe('shouldAutoDownloadUpdate', () => {
  it('triggers when a source install has an available update and no active task', () => {
    expect(shouldAutoDownloadUpdate('source', 'idle', 'update', true)).toBe(true)
  })

  it('triggers when a portable install has an available update and no active task', () => {
    expect(shouldAutoDownloadUpdate('portable', 'idle', 'update', true)).toBe(true)
  })

  it('triggers for a managed Docker install', () => {
    expect(shouldAutoDownloadUpdate('docker', 'idle', 'update', true)).toBe(true)
  })

  it('allows retry after a failed download', () => {
    expect(shouldAutoDownloadUpdate('source', 'failed', 'update', true)).toBe(true)
  })

  it('does not trigger when not entering via the update focus', () => {
    expect(shouldAutoDownloadUpdate('source', 'idle', '', true)).toBe(false)
  })

  it('does not trigger for unsupported modes', () => {
    expect(shouldAutoDownloadUpdate(null, 'idle', 'update', true)).toBe(false)
  })

  it('does not trigger while a download task is in progress', () => {
    expect(shouldAutoDownloadUpdate('source', 'downloading', 'update', true)).toBe(false)
    expect(shouldAutoDownloadUpdate('source', 'verifying', 'update', true)).toBe(false)
    expect(shouldAutoDownloadUpdate('source', 'applying', 'update', true)).toBe(false)
    expect(shouldAutoDownloadUpdate('source', 'restarting', 'update', true)).toBe(false)
  })

  it('allows downloading a newer version after a previous staged/done state', () => {
    // state/version 是上次更新的持久化结果，检测到新版本时不会重置。若上次
    // 残留 staged/done（属于旧版本）却因此拦截，弹窗“前往设置”后永远不自动
    // 下载。有新版本（updateAvailable=true）时应允许重新下载。
    expect(shouldAutoDownloadUpdate('source', 'staged', 'update', true)).toBe(true)
    expect(shouldAutoDownloadUpdate('source', 'done', 'update', true)).toBe(true)
  })

  it('does not trigger when no update is available', () => {
    expect(shouldAutoDownloadUpdate('source', 'idle', 'update', false)).toBe(false)
  })
})
