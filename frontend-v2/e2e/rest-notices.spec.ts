import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'
import { accessToken, PLAY_READY_TIMEOUT, seatTakeoverPath } from './support'

async function showNotices(page: Page, mobile: boolean) {
  const entry = page.getByTestId('rest-notices-open')
  if (!(await entry.isVisible())) {
    if (mobile) {
      await page.getByTestId('play-tools-toggle').click()
      await page.getByTestId('play-tools-panel').getByRole('button', { name: '队伍', exact: true }).click()
    } else {
      await page.getByTestId('play-party-rail').getByRole('button', { name: '展开侧栏', exact: true }).click()
    }
  }
  await entry.click()
  await expect(page.getByTestId('rest-notices-dialog')).toBeVisible()
}

test('rest requests and settlement reach the team without resizing chat; mute is personal and durable', async ({ page, browser, request }, info) => {
  test.setTimeout(90_000)
  const mobile = info.project.name === 'mobile'
  const key = `web|e2e-rest-notices-${info.project.name}|web_bot`
  const base = `/api/games/${encodeURIComponent(key)}/recovery`
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  const context = await browser.newContext({ viewport: mobile ? { width: 390, height: 844 } : { width: 1366, height: 900 } })
  try {
    const player = await context.newPage()
    const playerLive = player.waitForResponse(response => new URL(response.url()).pathname.endsWith('/sse') && response.status() === 200)
    await player.goto(await seatTakeoverPath(request, key, 'e2e-player'))
    await expect(player).toHaveURL(/#\/play\?/, { timeout: PLAY_READY_TIMEOUT })
    await expect(player.getByTestId('timeline')).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
    const gmLive = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/sse') && response.status() === 200)
    await page.goto(`/#/play?game=${encodeURIComponent(key)}`)
    await expect(page.getByTestId('timeline')).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
    await Promise.all([playerLive, gmLive])
    await expect(player.getByTestId('rest-notice-toast')).toHaveCount(0)
    const input = player.locator('.composer textarea').first()
    await input.focus()
    const before = await player.locator('.composer').boundingBox()

    const apply = async (action: string, data: Record<string, unknown>) => {
      const initial = await (await request.get(base, { headers })).json()
      const response = await request.post(`${base}/${action}`, { headers, data: {
        run_id: initial.run_id, expected_revision: initial.revision,
        operation_id: `notices-${info.project.name}-${action}-${Date.now()}`, ...data,
      } })
      const result = await response.json()
      expect(response.ok(), JSON.stringify(result)).toBe(true)
      return result
    }
    const requested = await apply('request', { kind: 'overnight', actor_uid: 'e2e-player' })
    await expect(player.getByTestId('rest-notice-toast')).toContainText('申请')
    await expect(page.getByTestId('rest-notice-toast')).toContainText('申请')
    await expect(input).toBeFocused()
    const after = await player.locator('.composer').boundingBox()
    expect(after!.y).toBeCloseTo(before!.y, 0)
    expect(after!.height).toBeCloseTo(before!.height, 0)
    const bounds = await player.getByTestId('rest-notice-toast').boundingBox()
    expect(bounds!.x).toBeGreaterThanOrEqual(0)
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(player.viewportSize()!.width)
    await player.screenshot({ path: info.outputPath('rest-request-notice.png'), scale: 'css' })
    await player.getByTestId('rest-notice-dismiss').click()
    await page.getByTestId('rest-notice-dismiss').click()

    await apply('approve', { source_id: requested.source_id })
    await expect(player.getByTestId('rest-notice-toast')).toContainText('结算完成')
    await expect(page.getByTestId('rest-notice-toast')).toContainText('结算完成')
    await player.getByTestId('rest-notice-mute').click()
    await expect(player.getByTestId('rest-notice-toast')).toHaveCount(0)
    await page.getByTestId('rest-notice-dismiss').click()

    // A different actor's request remains public, but the first player's
    // display preference cannot silence another browser or alter settlement.
    await apply('request', { kind: 'overnight', actor_uid: 'e2e-gm' })
    await expect(page.getByTestId('rest-notice-toast')).toContainText('申请')
    await expect(player.getByTestId('rest-notice-toast')).toHaveCount(0)
    await showNotices(player, mobile)
    await expect(player.getByTestId('rest-notices-list').locator('article')).toHaveCount(3)
    await expect(player.getByTestId('rest-notices-enabled')).not.toBeChecked()
    await expect(player.getByTestId('rest-notices-list')).toContainText('结算完成')
    const dialog = player.getByRole('dialog', { name: '休息动态', exact: true })
    const dialogBounds = await dialog.boundingBox()
    expect(dialogBounds!.width).toBeLessThanOrEqual(player.viewportSize()!.width)
    expect(await dialog.evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1)
    await player.screenshot({ path: info.outputPath('rest-notices-muted-history.png'), scale: 'css' })
    await player.getByTestId('rest-notices-close').click()
    await player.reload()
    await expect(player.getByTestId('timeline')).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
    await expect(player.getByTestId('rest-notice-toast')).toHaveCount(0)
    await showNotices(player, mobile)
    await expect(player.getByTestId('rest-notices-enabled')).not.toBeChecked()
  } finally {
    await context.close()
  }
})
