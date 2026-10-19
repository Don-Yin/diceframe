import { expect, test } from './fixtures'
import type { TestInfo } from '@playwright/test'
import { accessToken } from './support'

// These checks exercise the short, user-facing paths introduced by the content
// shelf. They deliberately use the temporary E2E server created by run_e2e.py.
function desktopOnly(info: TestInfo) {
  test.skip(info.project.name !== 'desktop', 'content journey contract runs once on desktop')
}

test('content navigation exposes the four content owners', async ({ page }, info) => {
  desktopOnly(info)
  await page.goto('/#/library')
  const nav = page.locator('.content-workspace-nav')
  await expect(nav).toBeVisible()
  for (const route of ['library', 'lorebook', 'modules', 'rules']) {
    await expect(nav.locator(`a[href="#/${route}"]`), route).toHaveCount(1)
  }
})

test('top navigation preserves game and player context when returning to play', async ({ page }, info) => {
  desktopOnly(info)
  await page.goto('/#/library?game=web%7Ce2e%7Cgm&user=alice&share=1&unrelated=discard')
  const play = page.locator('.app-header .desktop-nav').getByRole('link', { name: /游玩|Play/ })
  await expect(play).toHaveCount(1)
  const href = await play.getAttribute('href')
  expect(href).toContain('/play?')
  const query = new URLSearchParams(href?.split('?')[1])
  expect(Object.fromEntries(query)).toEqual({ game: 'web|e2e|gm', user: 'alice', share: '1' })
})

test('adventure shelf renders its cover asset within a compact card', async ({ page }, info) => {
  desktopOnly(info)
  await page.goto('/#/library')
  const card = page.getByTestId('library-adventure').first()
  await expect(card).toBeVisible()
  const cover = card.locator('.library-card-cover > img')
  await expect(cover).toBeVisible()
  await expect.poll(() => cover.evaluate(img => ({ loaded: (img as HTMLImageElement).complete, width: (img as HTMLImageElement).naturalWidth })))
    .toMatchObject({ loaded: true, width: expect.any(Number) })
  expect(await cover.evaluate(img => (img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  expect((await card.boundingBox())?.height).toBeLessThanOrEqual(440)
})

test('an adventure shelf card preserves its canonical source in create', async ({ page, request }, info) => {
  desktopOnly(info)
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  const enabled = await request.post('/api/plugins/e2e-module/start', { headers })
  expect(enabled.ok()).toBe(true)
  try {
    await page.goto('/#/library')
    await page.getByTestId('library-source-filter').selectOption('plugin')
    const card = page.getByTestId('library-adventure').filter({ hasText: 'e2e-module' }).first()
    await expect(card).toBeVisible()
    const start = card.getByTestId('library-start')
    await expect(start).toHaveAttribute('href', /adventure_id=.*module_id=e2e-module/)
    await start.click()
    await expect(page).toHaveURL(/#\/create\?adventure_id=.*module_id=e2e-module/)
    await expect(page.getByTestId('create-adventure-summary')).toContainText('e2e-module')
  } finally {
    const stopped = await request.post('/api/plugins/e2e-module/stop', { headers })
    expect(stopped.ok()).toBe(true)
  }
})

test('create wizard keeps the adventure name when moving next and back', async ({ page }, info) => {
  desktopOnly(info)
  await page.goto('/#/library')
  const card = page.getByTestId('library-adventure').first()
  await card.getByTestId('library-start').click()
  await expect(page.locator('.create-content-stage')).toBeVisible()
  const name = page.locator('.create-config-surface input').first()
  await name.fill('旅途中的新名字')
  await page.locator('.create-actions .primary').click()
  await expect(page.locator('.create-game-settings-stage')).toBeVisible()
  await page.locator('.create-actions').getByRole('button', { name: /上一步|Previous/ }).click()
  await expect(name).toHaveValue('旅途中的新名字')
})

test('returning to the shelf keeps the selected adventure draft available', async ({ page }, info) => {
  desktopOnly(info)
  await page.goto('/#/library')
  const card = page.getByTestId('library-adventure').first()
  const adventureName = await card.locator('h2').textContent()
  await card.getByTestId('library-start').click()
  const name = page.locator('.create-config-surface input').first()
  await name.fill('返回后仍保留')
  await page.locator('.create-back').click()
  await expect(page).toHaveURL(/#\/library/)
  await expect(page.getByTestId('library-adventure').filter({ hasText: adventureName || '' }).first()).toBeVisible()
  await page.getByTestId('library-adventure').filter({ hasText: adventureName || '' }).first().getByTestId('library-start').click()
  await expect(page.locator('.create-config-surface input').first()).toHaveValue('返回后仍保留')
})

test('library refuses to offer start when no installed runtime matches', async ({ page }, info) => {
  desktopOnly(info)
  await page.route('**/api/adventures?*', async route => route.fulfill({ json: {
    ok: true,
    adventures: [{ adventure_id: 'fixture:unavailable', name: 'Unavailable fixture', summary: 'No runtime', version: '1.0.0', source_kind: 'builtin', source_id: '', format: 'diceframe:adventure-graph-v2', required_runtime: { id: 'fixture:missing', minimum_version: 1 }, world_policy: 'portable', compatibility: 'incompatible', incompatibility_reasons: ['ruleset_runtime_unavailable'] }],
  } }))
  await page.route('**/api/rules?*', async route => route.fulfill({ json: { rules: [] } }))
  await page.goto('/#/library')
  const card = page.getByTestId('library-adventure')
  await expect(card).toContainText('Unavailable fixture')
  await expect(card.getByTestId('library-start')).toHaveCount(0)
  await expect(card).toContainText(/不可用|Unavailable/)
})

test('library shortcuts reach the adventure workbench and its review tools', async ({ page }, info) => {
  desktopOnly(info)
  const intents = [
    ['new', /新建冒险|New adventure/],
    ['script-import', /剧本|Script/],
    ['ai', /生成|Generate/],
    ['text-review', /文本|Text/],
  ] as const
  for (const [intent, modalName] of intents) {
    await page.goto(`/#/library`)
    if (intent === 'script-import') await page.locator('a[href*="/adventures?intent=script-import"]').click()
    else {
      await page.getByRole('link', { name: '冒险工作台', exact: true }).click()
      if (intent === 'new') await page.getByRole('button', { name: /新建冒险包|New adventure package/ }).click()
      else {
        await page.locator('.adventure-header-more > summary').click()
        await page.locator('.adventure-header-menu').getByRole('button', { name: intent === 'ai' ? /生成|Generate/ : /文本|text/i }).click()
      }
    }
    await expect(page).toHaveURL(/#\/adventures(?:\?|$)/)
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByRole('dialog')).toContainText(modalName)
    if (intent === 'ai') await expect(page.getByRole('dialog').getByRole('button', { name: /生成|Generate/ })).toBeVisible()
  }
})

test('package import intent opens the file importer without inventing a modal', async ({ page }, info) => {
  desktopOnly(info)
  await page.goto('/#/library')
  await page.getByRole('link', { name: '冒险工作台', exact: true }).click()
  await expect(page).toHaveURL(/#\/adventures(?:\?|$)/)
  await page.locator('.adventure-header-more > summary').click()
  const fileChooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /导入冒险包|Import adventure package|Import package/ }).click()
  await fileChooser
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('library and create entry points remain contained at desktop and phone widths', async ({ page }, info) => {
  desktopOnly(info)
  for (const theme of ['dark', 'light']) {
    for (const width of [1366, 375]) {
      await page.setViewportSize({ width, height: 844 })
      await page.goto('/#/library')
      await page.evaluate(value => localStorage.setItem('diceframe_mode_v2', value), theme)
      await page.reload()
      await expect(page.locator('html')).toHaveAttribute('data-mode', theme)
      await expect(page.getByTestId('content-library')).toHaveAttribute('aria-busy', 'false', { timeout: 30_000 })
      await expect(page.getByTestId('library-adventure').first()).toBeVisible({ timeout: 30_000 })
      await page.locator('.library-card-cover > img').evaluateAll(images => Promise.all(images.map(image => (image as HTMLImageElement).decode())))
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({ path: info.outputPath(`journey-library-${info.project.name}-${width}-${theme}-viewport.png`) })
      await page.screenshot({ path: info.outputPath(`journey-library-${info.project.name}-${width}-${theme}.png`), fullPage: true })
      await page.getByTestId('library-adventure').first().getByTestId('library-start').click()
      await expect(page.locator('.create-page')).toBeVisible()
      await expect(page.getByTestId('create-adventure-summary')).toBeVisible({ timeout: 30_000 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({ path: info.outputPath(`journey-create-${info.project.name}-${width}-${theme}-viewport.png`) })
      await page.screenshot({ path: info.outputPath(`journey-create-${info.project.name}-${width}-${theme}.png`), fullPage: true })
    }
  }
})

test('lorebook keeps the list and adjacent detail readable on desktop', async ({ page }, info) => {
  await page.setViewportSize({ width: 1366, height: 900 })
  await page.goto('/#/lorebook?world=default_fantasy')
  await expect(page.locator('.lore-row').first()).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath(`journey-lore-list-${info.project.name}-desktop.png`), fullPage: true })
  await page.locator('.lore-row').first().locator('.lore-entry-name').click()
  await expect(page.getByTestId('lore-entry-detail')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath(`journey-lore-detail-${info.project.name}-desktop.png`), fullPage: true })
})

test('lorebook opens a row detail, edits inline, saves, and returns on phone', async ({ page }, info) => {
  await page.setViewportSize({ width: 375, height: 844 })
  await page.goto('/#/lorebook?world=default_fantasy')
  await expect(page.locator('.lore-row').first()).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath(`journey-lore-list-${info.project.name}-375.png`), fullPage: true })
  const row = page.locator('.lore-row').first()
  await row.locator('.lore-entry-name').click()
  await expect(page.getByTestId('lore-entry-detail')).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath(`journey-lore-detail-${info.project.name}-375.png`), fullPage: true })
  await expect(page.locator('.lore-entry-list-pane')).toHaveCSS('display', 'none')
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  await page.getByTestId('lore-detail-edit').click()
  await expect(page.getByTestId('lore-inline-editor')).toBeVisible()
  const name = page.getByTestId('lore-inline-editor').locator('input').first()
  const original = await name.inputValue()
  await name.fill(`${original} · journey`)
  await page.locator('.content-workspace-nav a[href="#/library"]').click()
  const leaveDialog = page.getByRole('dialog')
  await expect(leaveDialog).toBeVisible()
  await leaveDialog.getByRole('button', { name: /继续编辑|Keep editing/ }).click()
  await expect(page).toHaveURL(/#\/lorebook/)
  await expect(page.getByTestId('lore-inline-editor')).toBeVisible()
  await expect(page.getByTestId('lore-inline-editor').locator('input').first()).toHaveValue(`${original} · journey`)
  await page.getByTestId('lore-inline-editor').getByRole('button', { name: /保存|Save/ }).click()
  await expect(page.getByTestId('lore-entry-detail')).toContainText('journey')
  await page.getByTestId('lore-detail-back').click()
  await expect(page.getByTestId('lore-entry-detail')).toHaveCount(0)
  await expect(page.locator('.lore-entry-list-pane')).toBeVisible()
})
