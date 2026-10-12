import { beforeEach, describe, expect, it, vi } from 'vitest'
import { securityApi } from '../src/api/security'
import { api } from '../src/api/client'
import { normalizeSettingsSection } from '../src/utils/settingsSections'

vi.mock('../src/api/client', () => ({
  api: vi.fn(),
}))

const apiMock = vi.mocked(api)

describe('securityApi', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockResolvedValue({ ok: true } as never)
  })

  it('reads transport status over GET', async () => {
    await securityApi.status()
    expect(apiMock).toHaveBeenCalledWith('/system/security/transport')
  })

  it('prepares self-signed mode with a POST body', async () => {
    await securityApi.prepare('self_signed')
    expect(apiMock).toHaveBeenCalledWith('/system/security/transport/prepare', {
      method: 'POST',
      body: JSON.stringify({ mode: 'self_signed' }),
    })
  })

  it('activates with the one-time preparation token', async () => {
    await securityApi.activate('token-1')
    expect(apiMock).toHaveBeenCalledWith('/system/security/transport/activate', {
      method: 'POST',
      body: JSON.stringify({ token: 'token-1' }),
    })
  })

  it('disables transport keeping the POST semantics', async () => {
    await securityApi.disable()
    expect(apiMock).toHaveBeenCalledWith('/system/security/transport/disable', { method: 'POST' })
  })

  it('regenerates the self-signed certificate', async () => {
    await securityApi.regenerate()
    expect(apiMock).toHaveBeenCalledWith(
      '/system/security/certificates/self-signed/regenerate',
      { method: 'POST' },
    )
  })
})

describe('settingsSections security entry', () => {
  it('accepts the security section from the route query', () => {
    expect(normalizeSettingsSection('security')).toBe('security')
  })

  it('keeps rejecting unknown sections', () => {
    expect(normalizeSettingsSection('tls')).toBeNull()
  })
})
