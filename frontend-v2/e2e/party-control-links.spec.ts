import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'
import { accessToken, PLAY_READY_TIMEOUT } from './support'

async function openParty(page: Page) {
  const rail = page.getByTestId('play-party-rail')
  if (!await rail.isVisible()) {
    await page.getByTestId('play-tools-toggle').click()
    await page.getByTestId('play-tools-panel').getByRole('button', { name: '队伍', exact: true }).click()
  }
  await expect(rail).toBeVisible()
  return rail
}

test('member menus group operations and preserve confirmation, link reuse and player isolation', async ({ page, request, browser }, info) => {
  test.setTimeout(75_000)
  const game = `web|e2e-party-control-links-${info.project.name}|web_bot`
  const path = `/api/games/${encodeURIComponent(game)}/players/e2e-player/seat-token`
  const prepared = await request.post(path, { headers: { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }, data: { rotate: true } })
  expect(prepared.ok()).toBe(true)
  const rotations: boolean[] = []
  page.on('request', request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === path) rotations.push(request.postDataJSON().rotate)
  })
  await page.goto(`/#/play?game=${encodeURIComponent(game)}`)
  await expect(page.getByTestId('timeline')).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
  const rail = await openParty(page)
  await expect(rail.getByTestId('party-member-menu')).toHaveCount(2)
  for (const width of info.project.name === 'mobile' ? [320, 390, 740] : [801, 980, 1280]) {
    await page.setViewportSize({ width, height: 900 })
    const rows = await rail.locator('.party-rail__member').evaluateAll(elements => elements.map(element => {
      const row = element.getBoundingClientRect()
      const text = element.querySelector('.party-rail__member-copy')!.getBoundingClientRect()
      const button = element.querySelector('button')!.getBoundingClientRect()
      return { gap: button.left - text.right, rightInset: row.right - button.right, height: button.height, overflow: element.scrollWidth - element.clientWidth }
    }))
    for (const row of rows) {
      expect(row.gap).toBeGreaterThanOrEqual(6)
      expect(row.rightInset).toBeGreaterThanOrEqual(6)
      expect(row.height).toBeGreaterThanOrEqual(32)
      expect(row.overflow).toBeLessThanOrEqual(1)
    }
    const members = (await rail.locator('.party-rail__members').boundingBox())!
    const invite = (await rail.getByTestId('play-invite-player').boundingBox())!
    expect(invite.y).toBeGreaterThan(members.y + members.height)
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  }
  await rail.screenshot({ path: info.outputPath('member-control-links.png'), scale: 'css', style: '[data-testid="assistant-shell-fab"] { visibility: hidden !important; }' })
  const control = rail.locator('[data-testid="party-member-menu"][data-player-id="e2e-player"]')
  await control.click()
  const menu = page.getByRole('menu', { name: '成员操作 · E2E Player', exact: true })
  await expect(menu.getByRole('menuitem')).toHaveText(['操作链接', '编辑', '暂离', '设为 AI', '踢出'])
  const menuBox = (await menu.boundingBox())!
  expect(menuBox.x).toBeGreaterThanOrEqual(0)
  expect(menuBox.x + menuBox.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  await page.screenshot({ path: info.outputPath('member-menu-open.png'), scale: 'css', animations: 'disabled' })
  await page.keyboard.press('Escape')
  await expect(menu).not.toBeVisible()
  const deletes: string[] = []
  page.on('request', request => { if (request.method() === 'DELETE') deletes.push(request.url()) })
  await control.click()
  await menu.getByRole('menuitem', { name: '踢出', exact: true }).click()
  const kickConfirmation = page.getByRole('dialog').filter({ hasText: '踢出玩家' })
  await expect(kickConfirmation).toBeVisible()
  await kickConfirmation.getByRole('button', { name: '取消', exact: true }).click()
  expect(deletes).toEqual([])
  await rail.locator('[data-testid="party-member-menu"][data-player-id="e2e-gm"]').click()
  await expect(page.getByRole('menuitem', { name: '踢出', exact: true })).toHaveCount(0)
  await page.keyboard.press('Escape')
  async function openControlLink() {
    await control.click()
    await page.getByRole('menuitem', { name: '操作链接', exact: true }).click()
  }
  await openControlLink()
  const confirmation = page.getByRole('dialog').filter({ hasText: '重新生成接管链接？' })
  await expect(confirmation).toBeVisible()
  await confirmation.getByRole('button', { name: '取消', exact: true }).click()
  expect(rotations).toEqual([false])
  await expect(page.getByRole('dialog', { name: '接管链接', exact: true })).toHaveCount(0)
  await openControlLink()
  await confirmation.getByRole('button', { name: '重新生成（旧设备下线）', exact: true }).click()
  const share = page.getByRole('dialog', { name: '接管链接', exact: true })
  await expect(share.locator('.invite-link')).toBeVisible()
  const link = (await share.locator('.invite-link').textContent())!
  const hash = new URL(link).hash
  expect(new URLSearchParams(hash.split('?')[1]).has('seat')).toBe(true)
  expect(rotations).toEqual([false, false, true])
  await share.getByRole('button', { name: '关闭', exact: true }).click()
  await openControlLink()
  await expect(share.locator('.invite-link')).toHaveText(link)
  await expect(confirmation).toHaveCount(0)
  expect(rotations).toEqual([false, false, true, false])
  await share.getByRole('button', { name: '关闭', exact: true }).click()
  await rail.getByTestId('play-invite-player').click()
  const invite = page.getByRole('dialog', { name: '邀请链接', exact: true })
  await expect(invite.locator('.invite-link')).toBeVisible()
  const invitation = new URL((await invite.locator('.invite-link').textContent())!)
  expect(new URLSearchParams(invitation.hash.split('?')[1]).has('seat')).toBe(false)
  const playerContext = await browser.newContext({ viewport: page.viewportSize()! })
  try {
    const player = await playerContext.newPage()
    await player.goto(`http://127.0.0.1:${process.env.TRPG_E2E_PORT || '18000'}/${hash}`)
    await expect(player.getByTestId('timeline')).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
    const playerRail = await openParty(player)
    await expect(playerRail.locator('.party-rail__member.is-self')).toContainText('E2E Player')
    await expect(playerRail.getByTestId('party-member-menu')).toHaveCount(0)
    await expect(playerRail.getByTestId('play-invite-player')).toHaveCount(0)
  } finally { await playerContext.close() }
})
