import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { test } from '@playwright/test'
import type { APIRequestContext, BrowserContext, Page } from '@playwright/test'

export const accessToken = () => {
  const dataDir = process.env.DICEFRAME_E2E_DATA_DIR
  if (!dataDir) throw new Error('DICEFRAME_E2E_DATA_DIR is required; run E2E through npm run test:e2e')
  return readFileSync(resolve(dataDir, 'access_token.txt'), 'utf8').trim()
}

async function announcementHash(request: APIRequestContext): Promise<string> {
  try {
    const response = await request.get('/api/announcements?lang=zh-CN')
    if (!response.ok()) return ''
    const payload = await response.json() as { hash?: unknown }
    return typeof payload.hash === 'string' ? payload.hash : ''
  } catch {
    return ''
  }
}

export async function prepareAuthenticatedPage(
  page: Page,
  request: APIRequestContext,
  options?: { light?: boolean },
) {
  const hash = await announcementHash(request)
  await page.addInitScript(({ token, hash, light }) => {
    localStorage.setItem('trpg_access_token', token)
    localStorage.setItem('diceframe_locale', 'zh-CN')
    if (hash) localStorage.setItem('diceframe_announcement_read_hash:zh', hash)
    if (light) {
      localStorage.setItem('diceframe_mode_v2', 'light')
      localStorage.setItem('diceframe_skin_v2', 'midnight')
      localStorage.removeItem('diceframe_plugin_theme_v2')
    }
  }, { token: accessToken(), hash, light: Boolean(options?.light) })
}

export async function prepareAuthenticatedContext(
  context: BrowserContext,
  request: APIRequestContext,
) {
  const hash = await announcementHash(request)
  await context.addInitScript(({ token, hash }) => {
    localStorage.setItem('trpg_access_token', token)
    localStorage.setItem('diceframe_locale', 'zh-CN')
    if (hash) localStorage.setItem('diceframe_announcement_read_hash:zh', hash)
  }, { token: accessToken(), hash })
}

/**
 * A GM takeover link for one seat: the owner issues that seat's token and the
 * player opens `#/join?…&seat=<token>`, exactly as a scanned control link.
 */
export async function seatTakeoverPath(
  request: APIRequestContext,
  gameKey: string,
  uid: string,
): Promise<string> {
  const url = `/api/games/${encodeURIComponent(gameKey)}/players/${encodeURIComponent(uid)}/seat-token`
  // The desktop and mobile projects take over the same fixture seat, so the
  // second issue is an explicit rotation.
  const init = { headers: { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }, data: { rotate: true } }
  let response = await request.post(url, init)
  // The whole smoke suite writes from one IP and can hit the per-IP write
  // budget; wait out the advertised window like a real client would.
  for (let attempt = 0; response.status() === 429 && attempt < 3; attempt += 1) {
    const body = await response.json().catch(() => ({})) as { retry_after?: number }
    const seconds = Math.min(Math.max(Number(body.retry_after) || 5, 1), 60)
    test.info().setTimeout(test.info().timeout + seconds * 1000)
    await new Promise(resolve => setTimeout(resolve, seconds * 1000))
    response = await request.post(url, init)
  }
  if (!response.ok()) throw new Error(`seat token issue failed: ${response.status()}`)
  const { seat_token: seat } = await response.json() as { seat_token: string }
  const params = new URLSearchParams({ game: gameKey, share: '1', seat })
  return `/#/join?${params.toString()}`
}

// Opening the play page POSTs claim-gm through retryOnRateLimit, which waits
// out a 429 of up to 10s once. The smoke suite writes from one IP and can hit
// the per-IP write budget, so the first readiness check must outlast that wait.
export const PLAY_READY_TIMEOUT = 20_000
