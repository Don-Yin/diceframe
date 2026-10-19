import { expect, test } from './fixtures'

const fixtureGames = {
  games: [{
    game_key: 'web|launcher-archive|web_bot',
    world_name: '悬浮球验收存档',
    scene: '雾港码头',
    rule_id: 'freeform_fantasy',
    state: 'active',
    solo_mode: true,
    player_count: 1,
    max_players: 4,
    round_number: 3,
    total_llm_calls: 2,
    total_tokens: 128,
  }],
}

async function mockOverviewGames(page: import('@playwright/test').Page) {
  await page.route('**/api/games', route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: fixtureGames })
    return route.continue()
  })
}

test('DF Agent launcher supports real mouse drag, persistence, clamping, and keyboard/tap opening', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'This covers real desktop mouse PointerEvents; touch coverage belongs to a separate mobile contract.')
  await mockOverviewGames(page)
  await page.setViewportSize({ width: 1024, height: 760 })
  await page.goto('/#/overview')

  const launcher = page.getByTestId('assistant-shell-fab')
  await expect(launcher).toBeVisible()
  const before = await launcher.boundingBox()
  expect(before).not.toBeNull()
  const target = { x: Math.max(20, before!.x - 180), y: Math.max(20, before!.y - 130) }
  await page.mouse.move(before!.x + before!.width / 2, before!.y + before!.height / 2)
  await page.mouse.down()
  await page.mouse.move(target.x + before!.width / 2, target.y + before!.height / 2, { steps: 8 })
  await page.mouse.up()

  await expect(page.locator('.assistant-panel')).toBeHidden()
  const afterDrag = await launcher.boundingBox()
  expect(afterDrag).not.toBeNull()
  expect(afterDrag!.x).toBeLessThan(before!.x - 40)
  expect(afterDrag!.y).toBeLessThan(before!.y - 40)
  const savedPosition = await page.evaluate(() => localStorage.getItem('diceframe_assistant_launcher_position'))
  expect(savedPosition).toBeTruthy()
  await page.screenshot({ path: info.outputPath('launcher-drag-desktop.png') })

  await page.reload()
  await expect(launcher).toBeVisible()
  const afterReload = await launcher.boundingBox()
  expect(afterReload).not.toBeNull()
  expect(afterReload!.x).toBeCloseTo(afterDrag!.x, 0)
  expect(afterReload!.y).toBeCloseTo(afterDrag!.y, 0)

  await page.setViewportSize({ width: 320, height: 640 })
  await expect.poll(async () => launcher.boundingBox()).toMatchObject({ x: expect.any(Number), y: expect.any(Number) })
  const narrow = await launcher.boundingBox()
  expect(narrow).not.toBeNull()
  expect(narrow!.x).toBeGreaterThanOrEqual(0)
  expect(narrow!.y).toBeGreaterThanOrEqual(0)
  expect(narrow!.x + narrow!.width).toBeLessThanOrEqual(320)
  expect(narrow!.y + narrow!.height).toBeLessThanOrEqual(640)

  // A short pointer click still opens after a drag.
  await launcher.click()
  await expect(page.locator('.assistant-panel')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.assistant-panel')).toBeHidden()

  // Keyboard activation reaches the same open path.
  await launcher.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('.assistant-panel')).toBeVisible()
})

test('DF Agent launcher supports a real mobile touch drag and short tap', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile', 'This uses Chromium CDP touch input on the Pixel 5 project.')
  await mockOverviewGames(page)
  await page.goto('/#/overview')

  const launcher = page.getByTestId('assistant-shell-fab')
  await expect(launcher).toBeVisible()
  const before = await launcher.boundingBox()
  expect(before).not.toBeNull()
  const start = { x: before!.x + before!.width / 2, y: before!.y + before!.height / 2 }
  const end = { x: Math.max(8, start.x - 110), y: Math.max(8, start.y - 100) }
  const cdp = await page.context().newCDPSession(page)
  try {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [start] })
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [end] })
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  } finally {
    await cdp.detach()
  }

  await expect(page.locator('.assistant-panel')).toBeHidden()
  const afterDrag = await launcher.boundingBox()
  expect(afterDrag).not.toBeNull()
  expect(afterDrag!.x).toBeLessThan(before!.x - 30)
  expect(afterDrag!.y).toBeLessThan(before!.y - 30)
  const savedPosition = await page.evaluate(() => localStorage.getItem('diceframe_assistant_launcher_position'))
  expect(savedPosition).toBeTruthy()

  await page.reload()
  await expect(launcher).toBeVisible()
  const afterReload = await launcher.boundingBox()
  expect(afterReload).not.toBeNull()
  expect(afterReload!.x).toBeCloseTo(afterDrag!.x, 0)
  expect(afterReload!.y).toBeCloseTo(afterDrag!.y, 0)
  expect(afterReload!.x).toBeGreaterThanOrEqual(0)
  expect(afterReload!.y).toBeGreaterThanOrEqual(0)
  expect(afterReload!.x + afterReload!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  expect(afterReload!.y + afterReload!.height).toBeLessThanOrEqual(page.viewportSize()!.height)

  await launcher.tap()
  await expect(page.locator('.assistant-panel')).toBeVisible()
  await expect(page.locator('.assistant-shell-expanded')).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('launcher-touch-mobile.png'), animations: 'disabled', scale: 'css' })
  const panelBox = await page.locator('.assistant-panel').boundingBox()
  expect(panelBox!.x).toBeGreaterThanOrEqual(0)
  expect(panelBox!.x + panelBox!.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1)
})

test('save archive art scales on hover/selection without moving text or action buttons', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'The art transform contract is measured with a stable desktop viewport.')
  await mockOverviewGames(page)
  await page.setViewportSize({ width: 1200, height: 800 })
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.goto('/#/overview')

  const card = page.locator('.game-card').first()
  const art = card.locator('.game-card-art')
  const title = card.locator('.game-card-body h2')
  const enter = card.locator('.game-card-enter')
  await expect(card).toBeVisible()
  await card.scrollIntoViewIfNeeded()
  const titleBefore = await title.boundingBox()
  const enterBefore = await enter.boundingBox()
  expect(titleBefore).not.toBeNull()
  expect(enterBefore).not.toBeNull()
  const readArtScale = () => art.evaluate(element => {
    const transform = getComputedStyle(element).transform
    return transform === 'none' ? 1 : new DOMMatrix(transform).a
  })
  const baseScale = await readArtScale()
  expect([1, 1.025]).toContainEqual(Number(baseScale.toFixed(3)))

  await card.hover()
  await expect.poll(readArtScale).toBeCloseTo(1.04, 2)
  await page.screenshot({ path: info.outputPath('save-art-hover.png') })
  const titleHover = await title.boundingBox()
  const enterHover = await enter.boundingBox()
  expect(titleHover).not.toBeNull()
  expect(enterHover).not.toBeNull()
  expect(Math.abs(titleHover!.x - titleBefore!.x)).toBeLessThanOrEqual(1)
  expect(Math.abs(titleHover!.y - titleBefore!.y)).toBeLessThanOrEqual(1)
  expect(Math.abs(enterHover!.x - enterBefore!.x)).toBeLessThanOrEqual(1)
  expect(Math.abs(enterHover!.y - enterBefore!.y)).toBeLessThanOrEqual(1)

  await page.mouse.move(8, 8)
  await expect.poll(readArtScale).toBeCloseTo(baseScale, 2)

  await page.getByTestId('overview-select-saves').click()
  const checkbox = card.getByRole('checkbox', { name: '选择存档' })
  await checkbox.check()
  await expect(card).toHaveClass(/is-selected/)
  await expect.poll(readArtScale).toBeCloseTo(1.04, 2)
  await checkbox.uncheck()
  await expect(card).not.toHaveClass(/is-selected/)
  await page.mouse.move(8, 8)
  await expect.poll(readArtScale).toBeCloseTo(baseScale, 2)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await card.hover()
  await expect.poll(readArtScale).toBeCloseTo(baseScale, 3)
  await expect.poll(() => art.evaluate(element => getComputedStyle(element).transitionDuration)).toBe('0s')
})
