import { expect, test } from './fixtures'
import { accessToken, prepareAuthenticatedContext, seatTakeoverPath } from './support'

// FIX-00：Play 页的 AdventurePanel 走的是 game-scoped 投影端点。owner 与分享
// 玩家都必须能读到，且分享玩家只能看到公开部分（GM 秘密节点不得下发）。
const ADVENTURE_GAME = 'web|e2e-adventure|web_bot'
const FREEFORM_GAME = 'web|e2e-room|web_bot'

test('freeform games keep the adventure entry and explain that no plan is bound', async ({ page }) => {
  await page.goto(`/#/play?game=${encodeURIComponent(FREEFORM_GAME)}`)
  const trigger = page.locator('.scene-trailing').getByTestId('adventure-panel-toggle')
  await expect(trigger).toBeVisible()
  await trigger.click()
  const panel = page.getByRole('dialog', { name: '冒险面板' })
  await expect(panel).toBeVisible()
  await expect(page.getByTestId('game-adventure-panel')).toHaveAttribute('aria-busy', 'false')
  await expect(panel).toContainText('本局未绑定冒险包')
  await expect(panel).toContainText('自由冒险')
})

test('adventure opens beside Checks without resizing chat at narrow and wide widths', async ({ page }, info) => {
  await page.goto(`/#/play?game=${encodeURIComponent(ADVENTURE_GAME)}`)
  for (const width of [320, 768, 1366]) {
    await page.setViewportSize({ width, height: width === 320 ? 640 : 900 })
    const trigger = page.locator('.scene-trailing').getByTestId('adventure-panel-toggle')
    await expect(trigger).toBeVisible()
    const before = await page.locator('.timeline').boundingBox()
    const header = page.locator('.scene-strip')
    expect(await header.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1)
    await trigger.click()
    const panel = page.getByRole('dialog', { name: '冒险面板' })
    await expect(panel).toBeVisible()
    await expect(page.getByTestId('game-adventure-panel')).toHaveAttribute('aria-busy', 'false')
    const after = await page.locator('.timeline').boundingBox()
    expect(after!.y).toBeCloseTo(before!.y, 0)
    expect(after!.height).toBeCloseTo(before!.height, 0)
    await page.screenshot({ path: info.outputPath(`adventure-${width}.png`) })
    await page.keyboard.press('Escape')
    await expect(panel).toHaveCount(0)
    await expect(trigger).toBeFocused()
  }
})

test('long adventure content scrolls with the wheel while the dialog heading stays visible', async ({ page, request }, info) => {
  const response = await request.get(`/api/games/${encodeURIComponent(ADVENTURE_GAME)}/adventure`, {
    headers: { Authorization: `Bearer ${accessToken()}` },
  })
  const payload = await response.json()
  payload.adventure.projection = {
    chapters: [{ id: 'scroll-chapter', name: 'Long adventure' }],
    nodes: Array.from({ length: 24 }, (_, index) => ({
      id: `scroll-${index}`, type: 'scene', chapter_id: 'scroll-chapter', name: `Scene ${index + 1}`,
      description: 'An extended scene description for a long adventure. '.repeat(8),
    })),
    objectives: [], milestones: [], progress: { active_nodes: [] },
  }
  await page.route('**/api/games/**/adventure?**', route => route.fulfill({ json: payload }))
  await page.setViewportSize(info.project.name === 'mobile' ? { width: 390, height: 640 } : { width: 1366, height: 800 })
  await page.goto(`/#/play?game=${encodeURIComponent(ADVENTURE_GAME)}`)
  await page.getByTestId('adventure-panel-toggle').click()
  const dialog = page.getByRole('dialog', { name: '冒险面板' })
  const body = page.getByTestId('game-adventure-panel')
  await expect(body).toHaveAttribute('aria-busy', 'false')
  await expect(body).toContainText('Scene 24')
  const heading = dialog.getByRole('heading', { name: '冒险面板', exact: true })
  const before = await heading.boundingBox()
  expect(await body.evaluate(element => element.scrollHeight - element.clientHeight)).toBeGreaterThan(100)
  await body.hover()
  await page.mouse.wheel(0, 700)
  await expect.poll(() => body.evaluate(element => element.scrollTop)).toBeGreaterThan(100)
  expect(await dialog.evaluate(element => element.scrollTop)).toBe(0)
  const after = await heading.boundingBox()
  expect(after!.y).toBeCloseTo(before!.y, 0)
  await page.screenshot({ path: info.outputPath('adventure-wheel-scrolled.png') })
  await page.getByTestId('adventure-panel-close').click()
  await expect(dialog).toHaveCount(0)
})

test('owner and shared player both read the bound adventure projection', async ({ browser, request }) => {
  const headers = { Authorization: `Bearer ${accessToken()}` }
  const chars = await (await request.get(
    `/api/games/${encodeURIComponent(ADVENTURE_GAME)}/characters`,
    { headers },
  )).json()
  const player = chars.players.find((item: any) => item.user_id !== 'e2e-gm') || chars.players[0]

  const gmContext = await browser.newContext()
  await prepareAuthenticatedContext(gmContext, request)
  const gmPage = await gmContext.newPage()
  await gmPage.setViewportSize({ width: 1366, height: 900 })
  const gmAdventureStatuses: number[] = []
  gmPage.on('response', response => {
    if (response.url().includes('/adventure')) gmAdventureStatuses.push(response.status())
  })
  await gmPage.goto(`/#/play?game=${encodeURIComponent(ADVENTURE_GAME)}`)

  const playerContext = await browser.newContext()
  const playerPage = await playerContext.newPage()
  await playerPage.setViewportSize({ width: 390, height: 844 })
  const playerAdventureStatuses: number[] = []
  playerPage.on('response', response => {
    if (response.url().includes('/adventure')) playerAdventureStatuses.push(response.status())
  })
  // A share player proves its seat with the seat token from a GM takeover link.
  await playerPage.goto(await seatTakeoverPath(request, ADVENTURE_GAME, player.user_id))
  // The rejoin may first wait out a short server rate limit (retried once).
  await expect(playerPage).toHaveURL(/#\/play\?/, { timeout: 20_000 })

  const gmPanel = gmPage.getByTestId('game-adventure-panel')
  const playerPanel = playerPage.getByTestId('game-adventure-panel')
  await expect(gmPanel).toHaveCount(0)
  await expect(playerPanel).toHaveCount(0)
  const gmComposer = await gmPage.locator('.composer').boundingBox()
  const playerComposer = await playerPage.locator('.composer').boundingBox()
  await gmPage.locator('.scene-trailing').getByTestId('adventure-panel-toggle').click()
  await playerPage.locator('.scene-trailing').getByTestId('adventure-panel-toggle').click()
  await expect(gmPage.getByRole('dialog', { name: '冒险面板' })).toBeVisible()
  await expect(playerPage.getByRole('dialog', { name: '冒险面板' })).toBeVisible()
  // GM 拿到完整图，分享玩家拿到过滤后的公开图。
  await expect(gmPanel).toContainText('E2E Secret Ritual')
  await expect(playerPanel).toContainText('E2E Public Gate')
  await expect(playerPanel).not.toContainText('E2E Secret Ritual')
  await expect(gmPanel.getByTestId('adventure-complete-public_gate')).toBeVisible()
  await expect(playerPanel.getByTestId('adventure-complete-public_gate')).toHaveCount(0)
  // 行动输入区仍然可见（Play 基础可用）。
  await expect(gmPage.locator('.composer')).toBeVisible()
  await expect(playerPage.locator('.composer')).toBeVisible()
  for (const [surface, before] of [[gmPage, gmComposer], [playerPage, playerComposer]] as const) {
    const after = await surface.locator('.composer').boundingBox()
    expect(after!.y).toBeCloseTo(before!.y, 0)
    expect(after!.height).toBeCloseTo(before!.height, 0)
    const dialog = await surface.getByRole('dialog', { name: '冒险面板' }).boundingBox()
    const viewport = surface.viewportSize()!
    expect(dialog!.x).toBeGreaterThanOrEqual(0)
    expect(dialog!.y).toBeGreaterThanOrEqual(0)
    expect(dialog!.x + dialog!.width).toBeLessThanOrEqual(viewport.width)
    expect(dialog!.y + dialog!.height).toBeLessThanOrEqual(viewport.height)
    await surface.getByTestId('adventure-panel-close').click()
    await expect(surface.getByTestId('game-adventure-panel')).toHaveCount(0)
    await expect(surface.getByTestId('adventure-panel-toggle')).toBeFocused()
  }
  expect(gmAdventureStatuses.length).toBeGreaterThan(0)
  expect(gmAdventureStatuses.every(status => status === 200)).toBe(true)
  expect(playerAdventureStatuses.length).toBeGreaterThan(0)
  expect(playerAdventureStatuses.every(status => status === 200)).toBe(true)

  await gmContext.close()
  await playerContext.close()
})
