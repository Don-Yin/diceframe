import { expect, test } from './fixtures'
import { PLAY_READY_TIMEOUT } from './support'

const playUrl = '/#/play?game=web%7Ce2e-room%7Cweb_bot'

for (const width of [1280, 390, 740]) test(`map location names share a fixed left edge at ${width}px`, async ({ page }, info) => {
  test.skip((width > 800) !== (info.project.name === 'desktop'), 'Cover desktop and narrow layouts once each.')
  await page.setViewportSize({ width, height: 844 })
  await page.route(url => url.pathname.startsWith('/api/games/') && url.pathname.endsWith('/map'), route => route.fulfill({ json: {
    current_location_id: 'house',
    locations: [
      { id: 'port', name: '港口', content: '地点一' },
      { id: 'university', name: '密斯卡托尼克大学', content: '地点二' },
      { id: 'house', name: '东街十七号二楼', content: '地点三' },
    ],
  } }))
  await page.goto(playUrl)
  await expect(page.getByTestId('play-tools-toggle')).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
  if (width <= 800) await page.getByTestId('play-tools-toggle').click()
  await page.getByRole('button', { name: '场景地图', exact: true }).click()
  const list = page.locator('.map-location-list')
  await expect(list.locator('button')).toHaveCount(3)
  const edges = await list.locator('strong').evaluateAll(elements => elements.map(element => element.getBoundingClientRect().left))
  expect(Math.max(...edges) - Math.min(...edges)).toBeLessThanOrEqual(1)
  await page.screenshot({ path: info.outputPath('map-location-list.png'), scale: 'css' })
  await list.getByRole('button', { name: /港口/ }).click()
  await expect(page.locator('.map-location-detail h3')).toHaveText('港口')
})

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 320, height: 844 },
  { width: 390, height: 844 },
  { width: 740, height: 360 },
]) test(`game tools stay anchored and reachable at ${viewport.width}x${viewport.height}`, async ({ page }, info) => {
  test.skip((viewport.width > 800) !== (info.project.name === 'desktop'), 'Use mouse on desktop and touch on narrow screens.')
  await page.setViewportSize(viewport)
  await page.goto(playUrl)
  const trigger = page.getByTestId('play-tools-toggle')
  await expect(trigger).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
  await trigger.click()
  const panel = page.getByTestId('play-tools-panel')
  await expect(panel).toBeVisible()
  await page.screenshot({ path: info.outputPath('game-tools.png') })
  const bounds = await panel.boundingBox()
  expect(bounds).not.toBeNull()
  expect(bounds!.x).toBeGreaterThanOrEqual(8)
  expect(bounds!.y).toBeGreaterThanOrEqual(8)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width - 8)
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(viewport.height - 8)

  const names = viewport.width <= 800
    ? ['角色', '场景地图', '队伍', '共享角色卡库', '场景画廊', '帮助', '刷新']
    : ['共享角色卡库', '场景画廊', '帮助', '刷新']
  for (const name of names) {
    const button = panel.getByRole('button', { name, exact: true })
    await button.scrollIntoViewIfNeeded()
    await expect(button).toBeVisible()
    const hit = await button.evaluate(element => {
      const box = element.getBoundingClientRect()
      return element.contains(document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2))
    })
    expect(hit, `${name} must be reachable, not clipped or covered`).toBe(true)
  }
  await panel.getByRole('button', { name: '帮助', exact: true }).click()
  await expect(panel).toBeHidden()
  await expect(page.getByRole('dialog', { name: '游玩帮助' })).toBeVisible()
})

test('DF Agent can open immediately after moving its launcher on the play page', async ({ page }, info) => {
  await page.goto(playUrl)
  await expect(page.getByTestId('play-tools-toggle')).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
  const launcher = page.getByTestId('assistant-shell-fab')
  await expect(launcher).toBeVisible()
  const before = (await launcher.boundingBox())!
  const start = { x: before.x + before.width / 2, y: before.y + before.height / 2 }
  // Moving outside the future drawer exposes event ordering that a launcher
  // kept near the right edge does not exercise.
  const end = { x: 64, y: start.y - 100 }
  if (info.project.name === 'mobile') {
    const cdp = await page.context().newCDPSession(page)
    try {
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [start] })
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [end] })
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    } finally { await cdp.detach() }
  } else {
    await page.mouse.move(start.x, start.y)
    await page.mouse.down()
    await page.mouse.move(end.x, end.y, { steps: 8 })
    await page.mouse.up()
  }
  await expect(page.locator('.assistant-panel')).toBeHidden()
  const after = (await launcher.boundingBox())!
  expect(after.x).toBeLessThan(before.x - 50)
  expect(after.y).toBeLessThan(before.y - 50)
  if (info.project.name === 'mobile') await launcher.tap()
  else await launcher.click()
  await page.screenshot({ path: info.outputPath('agent-after-drag.png') })
  await expect(page.locator('.assistant-panel')).toBeVisible()
  await expect.poll(async () => {
    const panel = (await page.locator('.assistant-panel').boundingBox())!
    return panel.x >= 0 && panel.x + panel.width <= page.viewportSize()!.width + 1
  }).toBe(true)
  await page.keyboard.press('Escape')
  await expect(page.locator('.assistant-panel')).toBeHidden()
  if (info.project.name === 'mobile') await launcher.tap()
  else await launcher.click()
  await expect(page.locator('.assistant-panel')).toBeVisible()
})
