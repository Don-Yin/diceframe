import { afterEach, describe, expect, it, vi } from 'vitest'

const connectionMocks = vi.hoisted(() => ({
  redirectToBackendLogin: vi.fn(),
}))

vi.mock('@/api/connection', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/connection')>(),
  redirectToBackendLogin: connectionMocks.redirectToBackendLogin,
}))

import { api, apiBlob, checkOwnerAccess, validateAccessToken } from '@/api/client'

describe('API client connection recovery', () => {
  afterEach(() => {
    connectionMocks.redirectToBackendLogin.mockReset()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it.each([
    ['JSON API', () => api('/config')],
    ['binary API', () => apiBlob('/assets/scene')],
    ['access-token validation', () => validateAccessToken('token')],
  ])('redirects after a network failure in %s requests', async (_label, request) => {
    const networkError = new TypeError('Failed to fetch')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(networkError))

    await expect(request()).rejects.toBe(networkError)
    expect(connectionMocks.redirectToBackendLogin).toHaveBeenCalledOnce()
  })

  it('redirects while reporting unavailable owner access after a network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(checkOwnerAccess()).resolves.toBe('unavailable')
    expect(connectionMocks.redirectToBackendLogin).toHaveBeenCalledOnce()
  })

  it('coalesces simultaneous owner-access probes without changing their result', async () => {
    let resolveFetch!: (response: Response) => void
    const fetchMock = vi.fn().mockReturnValue(new Promise<Response>((resolve) => {
      resolveFetch = resolve
    }))
    vi.stubGlobal('fetch', fetchMock)

    const first = checkOwnerAccess()
    const second = checkOwnerAccess()
    expect(fetchMock).toHaveBeenCalledOnce()

    resolveFetch(new Response('{}', { status: 200 }))
    await expect(Promise.all([first, second])).resolves.toEqual(['allowed', 'allowed'])
  })

  it('does not redirect when a DOM AbortError cancels a request', async () => {
    const abortError = new DOMException('Request cancelled', 'AbortError')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortError))

    await expect(api('/config')).rejects.toBe(abortError)
    expect(connectionMocks.redirectToBackendLogin).not.toHaveBeenCalled()
  })
})
