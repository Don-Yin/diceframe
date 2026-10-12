import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  accessTokenStorageKey,
  backendLoginUrl,
  buildApiUrl,
  currentBackendUrl,
  normalizeBackendUrl,
  redirectToBackendLogin,
  setBackendUrl,
} from '../src/api/connection'

describe('frontend connection', () => {
  beforeEach(() => {
    localStorage.clear()
    window.location.hash = ''
  })

  it('normalizes backend addresses without changing reverse proxy paths', () => {
    expect(normalizeBackendUrl('https://example.com/diceframe/')).toBe('https://example.com/diceframe')
    expect(normalizeBackendUrl('example.com:9876')).toBe('http://example.com:9876')
    expect(normalizeBackendUrl('javascript:alert(1)')).toBe('')
  })

  it('builds a reconnect URL that preserves the current route', () => {
    window.history.replaceState({}, '', '/#/settings?section=connection')
    expect(backendLoginUrl()).toBe('/#/login?redirect=%2F%23%2Fsettings%3Fsection%3Dconnection')
  })

  it('redirects a standalone frontend to login while preserving its route', () => {
    const assign = vi.fn()
    const target = {
      pathname: '/diceframe/',
      search: '?channel=preview',
      hash: '#/settings?section=connection',
      assign,
    }

    redirectToBackendLogin(true, target)

    expect(assign).toHaveBeenCalledWith(
      '/diceframe/?channel=preview#/login?redirect=%2Fdiceframe%2F%3Fchannel%3Dpreview%23%2Fsettings%3Fsection%3Dconnection',
    )
  })

  it('does not redirect bundled frontends or redirect the login page again', () => {
    const assign = vi.fn()
    const target = { pathname: '/', search: '', hash: '#/settings', assign }
    redirectToBackendLogin(false, target)
    redirectToBackendLogin(true, { ...target, hash: '#/login' })
    expect(assign).not.toHaveBeenCalled()
  })

  it('keeps external backend state isolated behind the standalone build flag', () => {
    setBackendUrl('https://example.com/diceframe')
    expect(currentBackendUrl()).toBe('')
    expect(buildApiUrl('/config')).toBe('/api/config')
    expect(accessTokenStorageKey()).toBe('trpg_access_token')
  })
})
