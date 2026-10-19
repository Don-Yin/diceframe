import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

const WORLD_ID = 'layout-world'
const GAME_KEY = 'web|layout-world|gm'

const ENTRY = {
  id: 'layout-entry',
  name: 'Layout entry',
  type: 'location',
  tier: 'core',
  keywords: ['layout'],
  content: 'A stable entry keeps the Lorebook list present while the shell is measured.',
  visible_to: ['*'],
}

async function installLorebookRoutes(page: Page) {
  await page.route('**/api/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = decodeURIComponent(url.pathname.replace(/^\/api/, ''))

    if (request.method() === 'GET' && path === '/announcements') {
      await route.fulfill({ json: { hash: 'lorebook-layout' } })
      return
    }
    if (request.method() === 'GET' && path === '/worlds') {
      await route.fulfill({ json: { worlds: [{ id: WORLD_ID, name: 'Layout World', language: 'zh-CN', entry_count: 1 }] } })
      return
    }
    if (request.method() === 'GET' && path === '/games') {
      await route.fulfill({ json: { games: [{ game_key: GAME_KEY, world_id: WORLD_ID, language: 'zh-CN' }] } })
      return
    }
    if (request.method() === 'GET' && path === `/games/${GAME_KEY}/characters`) {
      await route.fulfill({ json: { players: [] } })
      return
    }
    if (request.method() === 'GET' && path === '/lorebooks') {
      await route.fulfill({ json: { books: [
        { id: `world:${WORLD_ID}`, name: 'Layout World Book', primary: true, scope: 'world', enabled: true },
        { id: 'book:secondary', name: 'Secondary Book', scope: 'global', enabled: true },
      ] } })
      return
    }
    if (request.method() === 'GET' && (path === `/lorebook/${WORLD_ID}` || path === `/lorebooks/world:${WORLD_ID}/entries`)) {
      await route.fulfill({ json: { entries: [ENTRY] } })
      return
    }
    if (request.method() === 'GET' && path === `/lorebook/${WORLD_ID}/preview`) {
      await route.fulfill({ json: { ok: true, world_id: WORLD_ID, summary: { total: 1, visible: 1, public: 1, character_only: 0, gm_secret: 0 }, projections: { [ENTRY.id]: { entry_id: ENTRY.id, visible: true, visibility: 'public' } } } })
      return
    }
    await route.continue()
  })
}

type LayoutSnapshot = {
  contextCount: number
  legacySidebarCount: number
  legacyWorldBarCount: number
  contextRows: number
  context: { left: number; right: number; top: number; bottom: number; display: string; paddingTop: string; borderRadius: string; backgroundImage: string; backgroundColor: string }
  selections: Array<{ left: number; right: number; top: number; bottom: number }>
  workspace: { left: number; right: number; top: number; bottom: number }
  heading: { bottom: number }
  inspector: { left: number; right: number; top: number; bottom: number } | null
  viewport: { width: number; height: number }
  documentWidth: number
  light: boolean
}

async function snapshot(page: Page): Promise<LayoutSnapshot> {
  return page.evaluate(() => {
    const rectOf = (element: Element | null) => {
      if (!element) return null
      const rect = element.getBoundingClientRect()
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom }
    }
    const context = document.querySelector<HTMLElement>('.lore-context-bar')
    const style = context ? getComputedStyle(context) : null
    return {
      contextCount: document.querySelectorAll('.lore-context-bar').length,
      legacySidebarCount: document.querySelectorAll('.lorebook-sidebar, [class^="lorebook-sidebar__"]').length,
      legacyWorldBarCount: document.querySelectorAll('.lore-world-bar').length,
      contextRows: document.querySelectorAll('.lore-context-bar .lore-context-row').length,
      context: {
        ...(rectOf(context) || { left: 0, right: 0, top: 0, bottom: 0 }),
        display: style?.display || '',
        paddingTop: style?.paddingTop || '0px',
        borderRadius: style?.borderRadius || '0px',
        backgroundImage: style?.backgroundImage || 'none',
        backgroundColor: style?.backgroundColor || 'transparent',
      },
      selections: Array.from(document.querySelectorAll('.lore-context-row--world, .lore-context-row--book')).map(element => rectOf(element)!),
      workspace: rectOf(document.querySelector('.lorebook-workspace')) || { left: 0, right: 0, top: 0, bottom: 0 },
      heading: rectOf(document.querySelector('.lorebook-page h1')) || { bottom: 0 },
      inspector: rectOf(document.querySelector('.lore-perspective-inspector')),
      viewport: { width: window.innerWidth, height: window.innerHeight },
      documentWidth: document.documentElement.scrollWidth,
      light: document.body.classList.contains('light'),
    }
  })
}

async function assertLayout(page: Page, light: boolean) {
  await expect(page.locator('.lorebook-page')).toBeVisible()
  await expect(page.locator('.lore-context-bar')).toHaveCount(1)
  await expect(page.locator('.lore-context-bar .lore-context-select')).toHaveCount(2)
  await expect(page.locator('.lore-entry-toolbar')).toBeVisible()
  await expect(page.locator('.lore-row')).toHaveCount(1)

  const layout = await snapshot(page)
  expect(layout.light).toBe(light)
  expect(layout.legacySidebarCount).toBe(0)
  expect(layout.legacyWorldBarCount).toBe(0)
  expect(layout.contextRows).toBe(3)
  expect(layout.selections).toHaveLength(2)
  for (const selection of layout.selections) {
    expect(selection.left).toBeGreaterThanOrEqual(layout.context.left)
    expect(selection.right).toBeLessThanOrEqual(layout.context.right)
    expect(selection.top).toBeGreaterThanOrEqual(layout.context.top)
    expect(selection.bottom).toBeLessThanOrEqual(layout.context.bottom)
  }
  const [world, book] = layout.selections
  expect(world!.right <= book!.left + 1 || world!.bottom <= book!.top + 1).toBe(true)
  expect(Number.parseFloat(layout.context.paddingTop)).toBeGreaterThan(0)
  expect(Number.parseFloat(layout.context.borderRadius)).toBeGreaterThan(0)
  expect(layout.context.backgroundImage !== 'none' || layout.context.backgroundColor !== 'rgba(0, 0, 0, 0)').toBe(true)
  expect(layout.context.left).toBeGreaterThanOrEqual(layout.workspace.left - 1)
  expect(layout.context.right).toBeLessThanOrEqual(layout.workspace.right + 1)
  expect(layout.context.top).toBeGreaterThanOrEqual(layout.heading.bottom - 1)
  // Expanded mobile selectors are stacked and may need normal page scrolling.
  // Verify the last control can be reached instead of forcing it above the fold.
  const lastSelection = page.locator('.lore-context-select').last()
  await lastSelection.scrollIntoViewIfNeeded()
  await expect(lastSelection).toBeInViewport()
  expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewport.width + 1)

  if (layout.inspector) {
    expect(layout.inspector.right).toBeLessThanOrEqual(layout.viewport.width + 1)
    expect(layout.inspector.left).toBeGreaterThanOrEqual(layout.context.right - 1)
  }
}

test.describe('Lorebook layout regression', () => {
  test('keeps World → Book → Entry grouped and styled in dark and light themes', async ({ page }, testInfo) => {
    await page.addInitScript(() => {
      localStorage.setItem('currentGame', 'web|layout-world|gm')
      localStorage.setItem('lore_inspector_open', '1')
    })
    await installLorebookRoutes(page)

    await page.goto('/#/lorebook')
    await assertLayout(page, false)
    await page.screenshot({ path: testInfo.outputPath('lorebook-dark.png'), fullPage: true })

    await page.evaluate(() => localStorage.setItem('diceframe_mode_v2', 'light'))
    await page.reload()
    await assertLayout(page, true)
    await page.screenshot({ path: testInfo.outputPath('lorebook-light.png'), fullPage: true })
  })
})
