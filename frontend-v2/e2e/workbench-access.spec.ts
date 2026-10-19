import { expect, test } from './fixtures'
import { accessToken, seatTakeoverPath } from './support'

const GAME_KEY = 'web|e2e-room|web_bot'

test('workbench remains open after outside clicks and nested dialogs, and preserves drafts', async ({ page }, info) => {
  if (info.project.name === 'mobile') await page.setViewportSize({ width: 736, height: 844 })
  await page.goto(`/#/play?game=${encodeURIComponent(GAME_KEY)}`)
  const toggle = page.getByTestId('play-gm-toggle')
  await toggle.click()
  const drawer = page.getByTestId('play-gm-drawer')
  const workspace = page.getByTestId('gm-workspace')
  await workspace.getByRole('tab', { name: '设置', exact: true }).click()
  const command = workspace.locator('.gm-command-group input')
  await command.fill('keep this unfinished command')
  await page.mouse.click(4, 450)
  await expect(drawer).toHaveAttribute('aria-hidden', 'false')
  await expect(command).toHaveValue('keep this unfinished command')
  await workspace.getByRole('button', { name: '对局设置', exact: true }).click()
  const settings = page.getByRole('dialog', { name: '对局设置', exact: true })
  await expect(settings).toBeVisible()
  await expect(settings.locator('input[type="password"]')).toHaveCount(0)
  await settings.getByRole('button', { name: '取消', exact: true }).click()
  await expect(drawer).toHaveAttribute('aria-hidden', 'false')
  await expect(command).toHaveValue('keep this unfinished command')
  await page.screenshot({ path: info.outputPath('workbench-stays-open.png') })
  await drawer.locator('.rail-toggle').click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await toggle.click()
  await expect(command).toHaveValue('keep this unfinished command')
  await page.keyboard.press('Escape')
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
})

test('room password can be set and explicitly removed beside the invite action', async ({ page, request }, info) => {
  const headers = { Authorization: `Bearer ${accessToken()}` }
  const detailUrl = `/api/games/${encodeURIComponent(GAME_KEY)}`
  await page.goto(`/#/play?game=${encodeURIComponent(GAME_KEY)}`)
  const party = page.getByTestId('play-party-rail')
  if (info.project.name === 'mobile') {
    await page.getByTestId('play-tools-toggle').click()
    await page.getByTestId('play-tools-panel').getByRole('button', { name: '队伍', exact: true }).click()
  }
  await expect(party.getByTestId('play-invite-player')).toBeVisible()
  const password = party.getByTestId('play-room-password')
  await expect(password).toBeVisible()
  const inviteBox = await party.getByTestId('play-invite-player').boundingBox()
  const passwordBox = await password.boundingBox()
  expect(passwordBox!.y).toBeCloseTo(inviteBox!.y, 0)
  expect(passwordBox!.width).toBeCloseTo(inviteBox!.width, 0)
  await page.screenshot({ path: info.outputPath('party-access-actions.png') })
  await password.click()
  const dialog = page.getByRole('dialog', { name: '房间密码', exact: true })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByTestId('room-password-save')).toBeDisabled()
  await page.screenshot({ path: info.outputPath('room-password.png') })
  await dialog.getByTestId('room-password-input').fill('e2e-private-room')
  await dialog.getByTestId('room-password-save').click()
  await expect(dialog).toHaveCount(0)
  await expect.poll(async () => (await (await request.get(detailUrl, { headers })).json()).has_room_password).toBe(true)
  await password.click()
  await expect(dialog.getByTestId('room-password-status')).toContainText('已设置')
  await expect(dialog.getByTestId('room-password-input')).toHaveValue('')
  await dialog.getByTestId('room-password-remove').click()
  await expect(dialog).toHaveCount(0)
  await expect.poll(async () => (await (await request.get(detailUrl, { headers })).json()).has_room_password).toBe(false)
})

test('shared players have no room-password management entry', async ({ browser, request }) => {
  const playerContext = await browser.newContext()
  try {
    const page = await playerContext.newPage()
    await page.goto(await seatTakeoverPath(request, GAME_KEY, 'e2e-player'))
    await expect(page).toHaveURL(/#\/play\?/, { timeout: 20_000 })
    await expect(page.locator('.composer')).toBeVisible()
    await expect(page.getByTestId('play-room-password')).toHaveCount(0)
  } finally {
    await playerContext.close()
  }
})
