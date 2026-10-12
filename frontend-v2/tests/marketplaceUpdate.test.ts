import { describe, expect, it } from 'vitest'
import { isNewerPluginVersion, marketItemHasNewerVersion } from '../src/features/plugins/usePluginMarketplace'
import type { PluginMarketplaceItem } from '../src/api/types'

describe('marketItemHasNewerVersion', () => {
  const base: PluginMarketplaceItem = { id: 'demo', name: 'Demo' }

  it('returns true when latest.version is newer than installed', () => {
    expect(marketItemHasNewerVersion(
      { ...base, version: '1.0.0', latest: { version: '1.2.0', requires_approval: false } },
      '1.0.0',
    )).toBe(true)
  })

  it('returns false when latest.version equals installed', () => {
    expect(marketItemHasNewerVersion(
      { ...base, version: '1.0.0', latest: { version: '1.0.0', requires_approval: false } },
      '1.0.0',
    )).toBe(false)
  })

  it('falls back to item.version when latest is absent', () => {
    expect(marketItemHasNewerVersion({ ...base, version: '1.5.0' }, '1.0.0')).toBe(true)
    expect(marketItemHasNewerVersion({ ...base, version: '1.0.0' }, '1.0.0')).toBe(false)
  })

  it('returns false when the plugin is not installed', () => {
    expect(marketItemHasNewerVersion({ ...base, version: '1.0.0', latest: { version: '1.2.0' } }, undefined)).toBe(false)
  })

  it('treats requires_approval versions as newer when version is higher', () => {
    expect(marketItemHasNewerVersion(
      { ...base, version: '1.0.0', latest: { version: '2.0.0', requires_approval: true } },
      '1.0.0',
    )).toBe(true)
  })
})

describe('isNewerPluginVersion', () => {
  it('compares three-part versions', () => {
    expect(isNewerPluginVersion('1.2.0', '1.0.0')).toBe(true)
    expect(isNewerPluginVersion('1.0.0', '1.2.0')).toBe(false)
    expect(isNewerPluginVersion('1.0.0', '1.0.0')).toBe(false)
    expect(isNewerPluginVersion('v2.0.0', '1.9.9')).toBe(true)
  })

  it('compares normalized numeric version segments', () => {
    expect(isNewerPluginVersion('v1.2.1', '1.2.0')).toBe(true)
    expect(isNewerPluginVersion('1.10.0', '1.9.9')).toBe(true)
    expect(isNewerPluginVersion('1.2', '1.2.0')).toBe(false)
    expect(isNewerPluginVersion('1.1.9', '1.2.0')).toBe(false)
  })

  it('does not offer updates for incomplete versions', () => {
    expect(isNewerPluginVersion('', '1.0.0')).toBe(false)
    expect(isNewerPluginVersion('1.0.0', undefined)).toBe(false)
    expect(isNewerPluginVersion('nightly', '1.0.0')).toBe(false)
  })

  it('orders prerelease identifiers and ignores build metadata', () => {
    expect(isNewerPluginVersion('1.9.12-beta.3', '1.9.12-beta.2')).toBe(true)
    expect(isNewerPluginVersion('1.9.12-rc.1', '1.9.12-beta.9')).toBe(true)
    expect(isNewerPluginVersion('1.9.12', '1.9.12-rc.1')).toBe(true)
    expect(isNewerPluginVersion('1.9.12-beta.1', '1.9.12')).toBe(false)
    expect(isNewerPluginVersion('1.9.12+build.2', '1.9.12+build.1')).toBe(false)
  })
})
