import { expect, test } from './fixtures'
import type { Page, TestInfo } from '@playwright/test'

const ROOM_GAME = 'web|e2e-room|web_bot'
const COC_GAME = (project: string) => `web|e2e-dice-tray-${project}|web_bot`
const DND_GAME = 'web|e2e-dnd2024|web_bot'

async function assertNoHorizontalOverflow(page: Page, label: string) {
  const geometry = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth - window.innerWidth,
    overflowing: Array.from(document.querySelectorAll<HTMLElement>('body *'))
      .map(element => ({ element, rect: element.getBoundingClientRect() }))
      .filter(({ rect }) => rect.width > 0 && rect.right > window.innerWidth + 1)
      .slice(0, 8)
      .map(({ element, rect }) => `${element.tagName}.${String(element.className)}:${Math.round(rect.right)}`),
  }))
  expect(geometry.document, `${label}: document overflow ${JSON.stringify(geometry.overflowing)}`).toBeLessThanOrEqual(1)
}

async function setTheme(page: Page, light: boolean) {
  await page.evaluate(value => localStorage.setItem('diceframe_mode_v2', value ? 'light' : 'dark'), light)
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-mode', light ? 'light' : 'dark')
}

async function captureThemePage(page: Page, info: TestInfo, path: string, selector: string, name: string, light: boolean) {
  await page.goto(path)
  await setTheme(page, light)
  if (path.startsWith('/#/lorebook')) {
    await expect(page.getByTestId('lorebook-header')).toBeVisible()
    await page.getByTestId('lore-context-crumbs').click()
  }
  await expect(page.locator(selector).first()).toBeVisible()
  await expect(page.locator('.n-spin-body:visible')).toHaveCount(0)
  if (path.startsWith('/#/create')) {
    await expect(page.locator('.create-config-surface select').nth(0)).not.toHaveValue('')
    await expect(page.locator('.create-config-surface select').nth(1)).not.toHaveValue('')
  } else if (path.startsWith('/#/library')) {
    await expect(page.getByTestId('content-library')).toHaveAttribute('aria-busy', 'false')
  } else if (path.startsWith('/#/map')) {
    await expect(page.locator('.map-page-state[role="status"]')).toHaveCount(0)
  } else if (path.startsWith('/#/worlds')) {
    await expect(page.getByTestId('world-edit-lore').first()).toBeVisible()
  } else if (path.startsWith('/#/lorebook')) {
    await expect(page.locator('.lore-context-row--world select')).not.toHaveValue('')
    await expect(page.locator('.lore-book-static, select.lore-context-select[aria-label="当前资料册"]')).toHaveCount(1)
    await expect(page.locator('.lore-row').first()).toBeVisible()
  } else if (path.startsWith('/#/adventures')) {
    await expect(page.locator('.adventure-package-card').first()).toBeVisible()
  } else if (path.startsWith('/#/overview')) {
    await expect(page.locator('.game-card').first()).toBeVisible()
  } else if (path.startsWith('/#/characters')) {
    await expect(page.locator('.current-character-card').first()).toBeVisible()
  } else if (path.startsWith('/#/rules')) {
    await expect(page.locator('.rule-card').first()).toBeVisible()
  }
  await expect(page.getByRole('heading').first()).toBeVisible()
  await assertNoHorizontalOverflow(page, `${name} ${light ? 'light' : 'dark'}`)
  await page.screenshot({ path: info.outputPath(`${name}-${light ? 'light' : 'dark'}.png`), fullPage: true })
}

test('creator workshop links to the five existing creation tools', async ({ page }) => {
  await page.goto('/#/creator')
  await expect(page.getByTestId('creator-workshop')).toBeVisible()
  const routes = [
    ['adventures', 'adventures'],
    ['worlds', 'worlds'],
    ['lorebook', 'lorebook'],
    ['rules', 'rules'],
    ['modules', 'modules'],
  ] as const
  for (const [id, route] of routes) {
    await page.goto('/#/creator')
    const card = page.getByTestId(`creator-card-${id}`)
    await expect(card).toBeVisible()
    await expect(card).toHaveAttribute('href', new RegExp(`(?:#)?/${route}$`))
    await card.click()
    await expect(page).toHaveURL(new RegExp(`#/${route}(?:[?]|$)`))
  }
  await expect(page.getByText(/Profile|profile|玩法模板/i)).toHaveCount(0)
})

test('library world cards open the matching lorebook object for editing', async ({ page }) => {
  await page.goto('/#/library')
  await page.getByRole('link', { name: '世界', exact: true }).click()
  await expect(page.locator('.worlds-grid')).toBeVisible()
  const editLore = page.getByTestId('world-edit-lore').first()
  await expect(editLore).toBeVisible()
  const card = editLore.locator('xpath=ancestor::article[1]')
  const expectedWorldId = await card.getAttribute('data-world-id')
  expect(expectedWorldId).toBeTruthy()
  const cardText = await card.textContent()
  expect(cardText?.trim()).not.toBe('')
  await editLore.click()
  await expect(page).toHaveURL(/#\/lorebook\?world=[^&]+$/)
  const worldId = new URLSearchParams(page.url().split('?')[1]).get('world')
  expect(worldId).toBeTruthy()
  expect(worldId).toBe(expectedWorldId)
  const selector = page.locator('[data-testid="lore-context"] .lore-context-row--world select')
  await expect(selector).toHaveValue(worldId!)
  await page.getByTestId('lore-context-crumbs').click()
  await expect(page.getByTestId('lore-context')).toBeVisible()
})

test('world gallery cards keep their actions in a two by two grid', async ({ page }) => {
  await page.goto('/#/worlds')
  const card = page.locator('.world-card').first()
  await expect(card).toBeVisible()
  const actions = card.locator('.world-card-actions button')
  await expect(actions).toHaveCount(4)
  const boxes = await actions.evaluateAll(elements => elements.map(element => {
    const box = element.getBoundingClientRect()
    return { x: box.x, y: box.y, width: box.width }
  }))
  expect(Math.abs(boxes[0]!.y - boxes[1]!.y)).toBeLessThanOrEqual(1)
  expect(Math.abs(boxes[2]!.y - boxes[3]!.y)).toBeLessThanOrEqual(1)
  expect(boxes[2]!.y).toBeGreaterThan(boxes[0]!.y)
  expect(Math.abs(boxes[0]!.width - boxes[1]!.width)).toBeLessThanOrEqual(1)
  expect(Math.abs(boxes[2]!.width - boxes[3]!.width)).toBeLessThanOrEqual(1)
})

test('site management pages hold their controls in both themes on desktop and phone', async ({ page }, info) => {
  test.setTimeout(180_000)
  const desktop = info.project.name === 'desktop'
  await page.setViewportSize(desktop ? { width: 1366, height: 900 } : { width: 390, height: 844 })
  await page.addInitScript(game => localStorage.setItem('currentGame', game), ROOM_GAME)
  const pages = [
    ['overview', '/#/overview', '.overview-layout'],
    ['library', '/#/library', '[data-testid="content-library"]'],
    ['worlds', '/#/worlds', '.worlds-grid'],
    ['lorebook', '/#/lorebook', '[data-testid="lore-context"]'],
    ['create', '/#/create', '.create-page'],
    ['characters', '/#/characters?pane=current', '.characters-page'],
    ['map', `/#/map?game=${encodeURIComponent(ROOM_GAME)}`, '[data-testid="map-page"]'],
    ['settings', '/#/settings', '.settings-layout'],
    ['memory', '/#/memory', '.memory-search'],
    ['logs', '/#/logs', '.logs-workspace'],
    ['rules', '/#/rules', '.rules-page'],
    ['plugins', '/#/plugins', '.plugin-page'],
    ['creator', '/#/creator', '[data-testid="creator-workshop"]'],
    ['adventures', '/#/adventures', '[data-testid="adventure-creation-header"]'],
    ['module-detail', '/#/modules/e2e-module', '[data-testid="module-identity-note"]'],
  ] as const
  for (const [name, path, selector] of pages) {
    for (const light of [false, true]) {
      await captureThemePage(page, info, path, selector, `${name}-${desktop ? 'desktop' : 'mobile'}`, light)
      const visibleControls = page.locator('button:visible, a:visible, input:visible, select:visible, textarea:visible')
      await expect(visibleControls.first(), `${name} should expose a usable control`).toBeVisible()
    }
  }
})

test('desktop play keeps character status primary and GM controls in an on-demand drawer', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'desktop play layout contract')
  await page.setViewportSize({ width: 1366, height: 900 })
  await page.goto(`/#/play?game=${encodeURIComponent(ROOM_GAME)}`)
  await expect(page.getByTestId('timeline')).toBeVisible()
  await expect(page.locator('.composer')).toBeVisible()
  await expect(page.getByTestId('play-character-dock')).toBeVisible()

  const scene = page.locator('.scene-strip').first()
  const sceneHeight = await scene.evaluate(element => element.getBoundingClientRect().height)
  expect(sceneHeight).toBeLessThanOrEqual(52)

  const gmToggle = page.getByTestId('play-gm-toggle')
  await expect(gmToggle).toHaveAttribute('aria-expanded', 'false')
  await gmToggle.click()
  await expect(gmToggle).toHaveAttribute('aria-expanded', 'true')
  await expect(page.getByTestId('gm-workspace')).toBeVisible()
  const gmDrawer = page.getByTestId('play-gm-drawer')
  await expect(gmDrawer).toBeVisible()
  await page.screenshot({ path: info.outputPath('play-desktop-gm-tools.png'), fullPage: true })
  await gmDrawer.locator('.rail-toggle').click()
  await expect(gmToggle).toHaveAttribute('aria-expanded', 'false')
  await expect(gmDrawer).toHaveClass(/collapsed/)
  await gmToggle.click()
  await expect(gmDrawer.locator('.rail-toggle')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(gmToggle).toHaveAttribute('aria-expanded', 'false')
  await expect(gmToggle).toBeFocused()

  const chat = page.getByTestId('play-chat')
  await expect(chat).toBeVisible()
  const spaces = await page.evaluate(() => {
    const timeline = document.querySelector<HTMLElement>('[data-testid="timeline"]')!.getBoundingClientRect()
    const chat = document.querySelector<HTMLElement>('[data-testid="play-chat"]')!.getBoundingClientRect()
    return { timelineWidth: timeline.width, chatWidth: chat.width }
  })
  expect(spaces.timelineWidth).toBeGreaterThan(0)
  expect(spaces.chatWidth).toBeGreaterThan(0)
  expect(spaces.timelineWidth).toBeGreaterThanOrEqual(spaces.chatWidth - 50)
  await assertNoHorizontalOverflow(page, 'desktop play')
  await page.screenshot({ path: info.outputPath('play-desktop-character-first.png'), fullPage: true })
})

test('mobile play keeps quick status and its details action visible', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile', 'mobile play layout contract')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`/#/play?game=${encodeURIComponent(ROOM_GAME)}`)
  const quickStatus = page.getByTestId('play-quick-status')
  await expect(quickStatus).toBeVisible()
  await expect(quickStatus).toHaveAttribute('aria-label', /角色状态|Character status/)
  await page.screenshot({ path: info.outputPath('play-mobile-main.png'), fullPage: true })
  await quickStatus.click()
  await expect(page.locator('.play-sidebar-drawer.open')).toBeVisible()
  await expect(page.getByTestId('timeline')).toBeVisible()
  await expect(page.locator('.composer')).toBeVisible()
  const box = await quickStatus.boundingBox()
  expect(box?.height || 0).toBeGreaterThan(0)
  await assertNoHorizontalOverflow(page, 'mobile play')
  await page.screenshot({ path: info.outputPath('play-mobile-quick-status.png'), fullPage: true })
  await page.locator('.play-sidebar-drawer .sidebar-toggle').click()
  await page.getByTestId('play-gm-toggle').click()
  await expect(page.getByTestId('play-gm-drawer')).toBeVisible()
  await assertNoHorizontalOverflow(page, 'mobile GM tools')
  await page.screenshot({ path: info.outputPath('play-mobile-gm-tools.png'), fullPage: true })
})

test('CoC and D&D checks expose dice values only after a result is revealed', async ({ page }, info) => {
  test.setTimeout(120_000)
  await page.setViewportSize(info.project.name === 'desktop' ? { width: 1366, height: 900 } : { width: 390, height: 844 })
  const coc = COC_GAME(info.project.name)
  await page.goto(`/#/play?game=${encodeURIComponent(coc)}`)
  const cocCard = page.locator('.check-reveal-card').first()
  await expect(cocCard).toBeVisible()
  const sealedTray = page.getByTestId('dice-tray').first()
  await expect(sealedTray).toBeVisible()
  await expect(sealedTray.locator('[data-die-value]')).toHaveCount(0)
  await expect(page.locator('[data-die-value]:visible')).toHaveCount(0)
  await cocCard.locator('.check-reveal-actions button').click()
  const cocTray = page.getByTestId('dice-tray').first()
  await expect(cocTray).toBeVisible()
  await expect(cocTray.locator('[data-die-value]').first()).toBeVisible()
  const cocValues = await cocTray.locator('[data-die-value]').evaluateAll(items => items.map(item => item.getAttribute('data-die-value') || ''))
  expect(cocValues.length).toBeGreaterThan(0)
  expect(cocValues.every(value => /^\d+$/.test(value))).toBe(true)
  await cocCard.scrollIntoViewIfNeeded()
  await page.screenshot({ path: info.outputPath('coc-dice-tray.png'), fullPage: true })
  await page.reload()
  const toggle = page.getByTestId('dice-tray-toggle').first()
  await expect(toggle).toBeVisible()
  await toggle.click()
  await expect(page.getByTestId('dice-tray').first()).toBeVisible()
  await expect(page.locator('[data-die-value]:visible')).toHaveCount(cocValues.length)

  // The prepared D&D save has no check result yet. It must not fabricate a tray
  // or die values; a later authoritative result can populate the same surface.
  await page.goto(`/#/play?game=${encodeURIComponent(DND_GAME)}`)
  await expect(page.locator('.play-page')).toBeVisible()
  const dndTray = page.getByTestId('dice-tray').first()
  if (await dndTray.count()) {
    await expect(dndTray).toBeVisible()
    await expect(dndTray.locator('[data-die-value]')).toHaveCount(0)
  }
  await expect(page.locator('[data-die-value]:visible')).toHaveCount(0)
})
