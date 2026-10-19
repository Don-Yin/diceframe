import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'
import { accessToken, PLAY_READY_TIMEOUT, seatTakeoverPath } from './support'

async function openRecovery(page: Page) {
  const dock = page.getByTestId('play-character-dock')
  if (await dock.getAttribute('aria-hidden') === 'true') await page.getByTestId('play-character-toggle').click()
  const sidebar = dock.locator('.game-sidebar')
  if ((await sidebar.getAttribute('class'))?.includes('collapsed')) await sidebar.locator('.sidebar-toggle').click()
  const trigger = page.getByTestId('resource-recovery-open')
  await expect(trigger).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
  const characterBounds = await sidebar.locator('.character').boundingBox()
  const triggerBounds = await trigger.boundingBox()
  expect(triggerBounds!.y - characterBounds!.y - characterBounds!.height).toBeGreaterThanOrEqual(8)
  const before = await page.locator('.composer').boundingBox()
  await trigger.click()
  const dialog = page.getByRole('dialog', { name: '恢复 / 休整', exact: true })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText('加载中…', { exact: true })).toHaveCount(0)
  const after = await page.locator('.composer').boundingBox()
  expect(after!.y).toBeCloseTo(before!.y, 0)
  expect(after!.height).toBeCloseTo(before!.height, 0)
  const bounds = await dialog.boundingBox()
  const viewport = page.viewportSize()!
  expect(bounds!.x).toBeGreaterThanOrEqual(0)
  expect(bounds!.y).toBeGreaterThanOrEqual(0)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width)
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(viewport.height)
  expect(await dialog.evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1)
  return dialog
}

function savedState(key: string) {
  const folder = process.env.DICEFRAME_E2E_DATA_DIR
  if (!folder) throw new Error('Use scripts/run_e2e.py for isolated temporary recovery data')
  const state = JSON.parse(readFileSync(resolve(folder, 'saves', key.replaceAll('|', '#'), 'state.json'), 'utf8'))
  const clock = state.world_state.clock
  return { sanity: state.players['e2e-player'].character_sheet.sanity as number, minutes: (clock.day - 1) * 1440 + clock.minute as number }
}

test('real recovery: request, GM approval, durable receipt and player isolation without resizing chat', async ({ page, browser, request }, info) => {
  test.setTimeout(90_000)
  const key = `web|e2e-resource-recovery-${info.project.name}|web_bot`
  const base = `/api/games/${encodeURIComponent(key)}/recovery`
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  const initial = await (await request.get(base, { headers })).json()
  expect(initial.supported).toBe(true)
  expect(initial.blockers).toEqual([])
  // Create another actor's real source so player filtering is exercised rather
  // than merely asserting an empty authorization panel.
  const secretReason = `Keeper-private-reward-${info.project.name}`
  const reward = await request.post(`${base}/reward`, { headers, data: {
    run_id: initial.run_id, expected_revision: initial.revision, operation_id: `e2e-private-${info.project.name}`,
    actor_uid: 'e2e-gm', resource_key: 'sanity', resource_delta: 3, reason: secretReason,
  } })
  expect(reward.ok()).toBe(true)
  const ownerSource = (await reward.json()).source_id
  const context = await browser.newContext({ viewport: info.project.name === 'mobile' ? { width: 390, height: 844 } : { width: 1366, height: 900 } })
  try {
    const player = await context.newPage()
    await player.goto(await seatTakeoverPath(request, key, 'e2e-player'))
    await expect(player).toHaveURL(/#\/play\?/, { timeout: PLAY_READY_TIMEOUT })
    await expect(player.getByTestId('timeline')).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
    const playerDialog = await openRecovery(player)
    await expect(playerDialog.getByTestId('recovery-gm-tools')).toHaveCount(0)
    await expect(playerDialog).not.toContainText(secretReason)
    const before = savedState(key)
    expect(before).toEqual({ sanity: 40, minutes: 0 })
    const submitted = player.waitForResponse(response => new URL(response.url()).pathname.endsWith('/recovery/request') && response.request().method() === 'POST')
    await playerDialog.getByTestId('recovery-request-overnight').click()
    const requested = await (await submitted).json()
    expect(requested.ok).toBe(true)
    const sourceId = requested.source_id as string
    await expect(playerDialog).toContainText('待 GM 批准')
    expect(savedState(key)).toEqual(before)
    expect(requested.sources.map((source: { actor_uid: string }) => source.actor_uid)).toEqual(['e2e-player'])
    expect(requested.sources.some((source: { source_id: string }) => source.source_id === ownerSource)).toBe(false)
    await player.screenshot({ path: info.outputPath('recovery-player-pending.png'), scale: 'css' })

    await page.goto(`/#/play?game=${encodeURIComponent(key)}`)
    await expect(page.getByTestId('timeline')).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
    const gmDialog = await openRecovery(page)
    await expect(gmDialog.getByTestId('recovery-gm-tools')).toBeVisible()
    await expect(gmDialog).toContainText(secretReason)
    const approve = gmDialog.getByTestId(`recovery-approve-${sourceId}`)
    await expect(approve).toBeEnabled()
    let writes = 0
    page.on('request', req => { if (new URL(req.url()).pathname.endsWith('/recovery/approve')) writes++ })
    const approvedResponse = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/recovery/approve') && response.request().method() === 'POST')
    // Two immediate clicks must share the in-flight guard, never issue a second
    // approval with a fresh operation ID.
    await approve.evaluate(element => { (element as HTMLButtonElement).click(); (element as HTMLButtonElement).click() })
    const approvedHttp = await approvedResponse
    expect(approvedHttp.ok()).toBe(true)
    const approved = await approvedHttp.json()
    expect(approved.receipt.before).toBe(40)
    expect(approved.receipt.after).toBeGreaterThanOrEqual(41)
    expect(approved.receipt.after).toBeLessThanOrEqual(46)
    expect(approved.receipt.time_advanced_minutes).toBe(480)
    await expect(approve).toHaveCount(0)
    await expect(gmDialog).toContainText(`40 → ${approved.receipt.after}`)
    expect(writes).toBe(1)
    expect(savedState(key)).toEqual({ sanity: approved.receipt.after, minutes: 480 })
    // A network retry goes through the real HTTP replay path and may not add
    // SAN or world time for a second time.
    // Use the same authenticated browser session: an independent APIRequest
    // context has its own principal even if both sessions have owner access.
    const replay = await page.request.post(approvedHttp.url(), { headers, data: approvedHttp.request().postDataJSON() })
    const replayed = await replay.json()
    expect(replay.ok(), JSON.stringify(replayed)).toBe(true)
    expect(replayed.duplicate).toBe(true)
    expect(savedState(key)).toEqual({ sanity: approved.receipt.after, minutes: 480 })
    await page.screenshot({ path: info.outputPath('recovery-gm-settled.png'), scale: 'css' })

    await playerDialog.getByRole('button', { name: '刷新', exact: true }).click()
    await expect(playerDialog).toContainText(`40 → ${approved.receipt.after}`)
    await expect(playerDialog).toContainText('已结算')
    await expect(playerDialog).not.toContainText(secretReason)
    await expect(playerDialog.getByTestId('recovery-gm-tools')).toHaveCount(0)
    await player.screenshot({ path: info.outputPath('recovery-player-settled.png'), scale: 'css' })
    await playerDialog.getByRole('button', { name: '关闭', exact: true }).click()
    await expect(player.getByRole('dialog', { name: '恢复 / 休整', exact: true })).toHaveCount(0)
    await expect(player.getByTestId('resource-recovery-open')).toBeFocused()
  } finally { await context.close() }
})
