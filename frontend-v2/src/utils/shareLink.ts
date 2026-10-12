const URL_SCHEME_RE = /^[a-z][a-z0-9+.-]*:\/\//i

/** 浏览器当前打开前端用的 origin；没有 window 时（SSR / 测试）给一个可解析的占位。 */
export function currentOrigin(): string {
  return typeof window === 'undefined' ? 'http://localhost' : window.location.origin
}

const fallbackOrigin = currentOrigin
/** `new URL()` 对 IPv6 字面量给出的 hostname 带方括号，裸写的 ::1 也要认。 */
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '[::1]'])

/**
 * 地址是否只指向本机。
 *
 * host 明确是回环地址时，其它设备必然打不开——这是不做网络探测就能下的唯一
 * 可靠判断，用来决定「仅本机可访问」的提示，而不是用来阻止任何操作。
 */
export function isLoopbackUrl(value: string): boolean {
  try {
    return LOOPBACK_HOSTS.has(new URL(value).hostname.toLowerCase())
  } catch {
    return false
  }
}

/**
 * 把一段地址的 host 换成另一个，scheme、端口与路径保持原样。
 *
 * 服务端只知道「本机有哪些网卡地址可达」（GET /api/system/network 给的是 host），
 * 不知道浏览器是从哪个端口打开前端的：独立前端跑在自己的端口上，内置前端与后端
 * 同端口。所以换 host 而不是整段 URL——同一份候选 host 才能同时用于前端加入
 * 地址和后端服务地址。
 */
export function withHost(base: string, host: string): string {
  const bare = String(host || '').trim()
  if (!bare) return ''
  // IPv6 字面量必须带方括号，否则拼出来的不是合法 URL。
  const literal = bare.includes(':') && !bare.startsWith('[') ? `[${bare}]` : bare
  try {
    const parsed = new URL(base)
    const port = parsed.port ? `:${parsed.port}` : ''
    return `${parsed.protocol}//${literal}${port}${parsed.pathname.replace(/\/+$/, '')}`
  } catch {
    return ''
  }
}

export function normalizePublicBaseUrl(value?: string): string {
  const raw = String(value || '').trim()
  if (!raw) return fallbackOrigin()

  const candidate = URL_SCHEME_RE.test(raw) ? raw : `http://${raw}`
  try {
    const parsed = new URL(candidate)
    const path = parsed.pathname.replace(/\/+$/, '')
    return `${parsed.origin}${path}`
  } catch {
    return fallbackOrigin()
  }
}

/**
 * Player join link. A takeover link for one seat carries that seat's token in
 * the hash route (`seat`), never the public uid: the hash never reaches the
 * server or proxy logs, and JoinView strips it from the address bar at once.
 */
export function buildJoinLink(gameKey: string, publicBaseUrl?: string, seatToken?: string, backendUrl?: string): string {
  const base = normalizePublicBaseUrl(publicBaseUrl).replace(/\/+$/, '')
  const url = new URL(`${base}/`)
  const params = new URLSearchParams({ game: gameKey, share: '1' })
  if (seatToken) params.set('seat', seatToken)
  const server = normalizePublicBaseUrl(backendUrl)
  if (backendUrl && server) params.set('server', server)
  url.hash = `/join?${params.toString()}`
  return url.toString()
}

/**
 * 移动端扫码登录的二维码载荷。
 *
 * 用 App 自己的 scheme 而不是 http 链接：这段内容只对 DiceFrame App 有意义，
 * 用 http 反而会让系统相机把 GM 引到浏览器里去。配对码是一次性短时效凭据，
 * 出现在二维码里是设计的一部分（见后端 src/webui/pairing.py）。
 */
export function buildPairingPayload(backendUrl: string, code: string): string {
  const params = new URLSearchParams({ s: normalizePublicBaseUrl(backendUrl), c: code })
  return `diceframe://pair?${params.toString()}`
}
