const BACKEND_URL_KEY = 'trpg_backend_url'
const ACCESS_TOKEN_KEY = 'trpg_access_token'
const HTTP_SCHEME_RE = /^https?:\/\//i

type ConnectionLocation = Pick<Location, 'pathname' | 'search' | 'hash'>
type ConnectionNavigation = ConnectionLocation & Pick<Location, 'assign'>

function hashQuery(): URLSearchParams {
  if (typeof location === 'undefined') return new URLSearchParams()
  return new URLSearchParams(location.hash.split('?')[1] || '')
}

export function isStandaloneFrontend(): boolean {
  return typeof __DF_STANDALONE__ !== 'undefined' && __DF_STANDALONE__
}

export function normalizeBackendUrl(value: string): string {
  let raw = String(value || '').trim()
  if (!raw) return ''
  if (!HTTP_SCHEME_RE.test(raw)) raw = `http://${raw}`
  try {
    const parsed = new URL(raw)
    if (!['http:', 'https:'].includes(parsed.protocol)) return ''
    if (parsed.username || parsed.password || parsed.search || parsed.hash) return ''
    return `${parsed.origin}${parsed.pathname.replace(/\/+$/, '')}`
  } catch {
    return ''
  }
}

export function backendUrlFromShareLink(): string {
  return normalizeBackendUrl(hashQuery().get('server') || '')
}

export function currentBackendUrl(): string {
  if (!isStandaloneFrontend()) return ''
  const fromShare = backendUrlFromShareLink()
  if (fromShare) {
    if (typeof localStorage !== 'undefined') localStorage.setItem(BACKEND_URL_KEY, fromShare)
    return fromShare
  }
  if (typeof localStorage === 'undefined') return ''
  return normalizeBackendUrl(localStorage.getItem(BACKEND_URL_KEY) || '')
}

export function setBackendUrl(value: string): string {
  const normalized = normalizeBackendUrl(value)
  if (!normalized) throw new Error('invalid-backend-url')
  localStorage.setItem(BACKEND_URL_KEY, normalized)
  return normalized
}

export function backendLoginUrl(target: ConnectionLocation = location): string {
  const currentLocation = `${target.pathname}${target.search}${target.hash}`
  return `${target.pathname}${target.search}#/login?redirect=${encodeURIComponent(currentLocation)}`
}

export function redirectToBackendLogin(
  standalone = isStandaloneFrontend(),
  target: ConnectionNavigation | undefined = typeof location === 'undefined' ? undefined : location,
): void {
  if (!standalone || !target || target.hash.startsWith('#/login')) return
  target.assign(backendLoginUrl(target))
}

export function accessTokenStorageKey(): string {
  const backend = currentBackendUrl()
  return backend ? `${ACCESS_TOKEN_KEY}:${encodeURIComponent(backend)}` : ACCESS_TOKEN_KEY
}

export function buildApiUrl(path: string): string {
  const route = `/api${path}`
  const backend = currentBackendUrl()
  return backend ? `${backend}${route}` : route
}
