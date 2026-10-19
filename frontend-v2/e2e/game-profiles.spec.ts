import { expect, test } from './fixtures'
import { accessToken, seatTakeoverPath } from './support'

for (const profile of ['heist', 'survival']) test(`creates and plays ${profile} through its capability panel and shared player page`, async ({ page, browser, request }, info) => {
  // Profile creation remains a supported capability, but its experimental
  // launcher is intentionally absent from ordinary /create. Exercise the
  // existing profile API directly, then verify the same PlayEntry/ProfileBoard
  // route and authority behavior as before.
  const createResponse = await request.post('/api/game-profiles/create', {
    headers: { Authorization: `Bearer ${accessToken()}` },
    data: {
      profile_id: `core:demo-${profile}`,
      name: profile === 'heist' ? 'Heist' : 'Survival',
      names: ['Leader', 'Scout'],
      language: 'zh-CN',
    },
  })
  const result = await createResponse.json()
  expect(createResponse.ok(), JSON.stringify(result)).toBe(true)
  expect(result.ok, JSON.stringify(result)).toBe(true)
  const key = result.game_key, path = `/api/games/${encodeURIComponent(key)}`
  const detailResponse = await request.get(path, { headers: { Authorization: `Bearer ${accessToken()}` } })
  const detail = await detailResponse.json()
  expect(detailResponse.ok(), JSON.stringify(detail)).toBe(true)
  expect(detail.game_profile, JSON.stringify(detail)).toMatchObject({ id: `core:demo-${profile}` })
  const profileResponse = await request.get(`${path}/profile`, { headers: { Authorization: `Bearer ${accessToken()}` } })
  const profileView = await profileResponse.json()
  expect(profileResponse.ok(), JSON.stringify(profileView)).toBe(true)
  expect(profileView.profile, JSON.stringify(profileView)).toMatchObject({ id: `core:demo-${profile}` })
  await expect(key).toBeTruthy()
  await page.goto(`/#/play?game=${encodeURIComponent(key)}`)
  const board = page.getByTestId('profile-board')
  await expect(board).toBeVisible()
  await expect(page.locator('.composer')).toHaveCount(0)
  await board.getByTestId(`profile-move-${profile === 'heist' ? 'study' : 'forage'}`).click()
  await expect(board.locator('.profile-history li')).toHaveCount(1)
  await board.getByTestId('profile-advance').click()
  await expect(board.locator('.profile-history li')).toHaveCount(2)
  if (profile === 'heist') {
    await expect(board.locator('.profile-time')).toContainText('行动')
    await board.getByTestId('profile-control').click()
    await expect(board.getByTestId('profile-auto')).toBeVisible()
    await board.getByTestId('profile-auto').click()
    await expect(board.locator('.profile-history li')).toHaveCount(3)
    await board.getByTestId('profile-control').click()
  } else await expect(board.locator('.profile-time')).toContainText('2')
  const view = await (await request.get(`${path}/profile`, { headers: { Authorization: `Bearer ${accessToken()}` } })).json()
  const playerUid = view.actors.find((actor: { uid: string }) => actor.uid !== view.gm_uid).uid
  const playerContext = await browser.newContext({ viewport: { width: 390, height: 844 } })
  try {
    const player = await playerContext.newPage()
    await player.goto(await seatTakeoverPath(request, key, playerUid))
    const playerBoard = player.getByTestId('profile-board')
    await expect(playerBoard).toBeVisible()
    await expect(playerBoard.getByTestId('profile-advance')).toHaveCount(0)
    await expect(playerBoard.getByTestId('profile-control')).toHaveCount(0)
    await playerBoard.getByTestId(`profile-move-${profile === 'heist' ? 'sneak' : 'forage'}`).click()
    await expect(playerBoard.locator('.profile-history li')).toHaveCount(profile === 'heist' ? 4 : 3)
    await player.reload()
    await expect(playerBoard.locator('.profile-history li')).toHaveCount(profile === 'heist' ? 4 : 3)
    const geometry = await playerBoard.evaluate(element => ({ overflow: document.documentElement.scrollWidth - innerWidth, right: element.getBoundingClientRect().right, width: innerWidth }))
    expect(geometry.overflow).toBeLessThanOrEqual(1)
    expect(geometry.right).toBeLessThanOrEqual(geometry.width)
    const refresh = await playerBoard.getByTestId('profile-refresh').boundingBox()
    const themeToggle = player.getByRole('button', { name: /切换到.*主题|Switch to .*theme/i })
    await expect(themeToggle).toHaveCount(1)
    const theme = await themeToggle.boundingBox()
    expect(refresh).not.toBeNull(); expect(theme).not.toBeNull()
    expect(refresh!.y >= theme!.y + theme!.height || refresh!.x + refresh!.width <= theme!.x).toBe(true)
    const previousTheme = await player.locator('body').evaluate(element => element.classList.contains('light'))
    await themeToggle.click()
    await expect.poll(() => player.locator('body').evaluate(element => element.classList.contains('light'))).toBe(!previousTheme)
    await player.screenshot({ path: info.outputPath(`${profile}-player.png`), fullPage: true })
  } finally { await playerContext.close() }
  await page.reload()
  await expect(board.locator('.profile-history li')).toHaveCount(profile === 'heist' ? 4 : 3)
})
