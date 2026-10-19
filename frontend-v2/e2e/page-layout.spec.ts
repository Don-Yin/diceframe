import { expect, test } from './fixtures'
import type { Page } from '@playwright/test'

/**
 * The section pages share one page frame.  Keep this contract at the browser
 * boundary because a route can look correct on its own while still jumping
 * when the user moves between Content, Characters, and Management.
 */
const sectionPages = [
  { route: 'overview', frame: '.overview-page', heading: '.overview-hero' },
  { route: 'characters', frame: '.characters-page', heading: '.characters-page-heading' },
  { route: 'plugins', frame: '.plugin-page', heading: '.plugin-workspace > .archive-hero' },
  { route: 'settings', frame: '.settings-page', heading: '.settings-page-heading' },
  { route: 'memory', frame: '.memory-page', heading: '.memory-page-heading' },
  { route: 'library', frame: '.content-library', heading: '.library-heading' },
  { route: 'modules', frame: '.modules-page', heading: '.modules-heading' },
  { route: 'lorebook', frame: '.lorebook-page', heading: '[data-testid="lorebook-header"]' },
  { route: 'worlds', frame: '.worlds-page', heading: '.worlds-page-heading' },
  { route: 'rules', frame: '.rules-page', heading: '.rules-page-heading' },
  { route: 'creator', frame: '.creator-workshop', heading: '.content-page-heading' },
] as const

type Geometry = {
  route: string
  frame: { x: number; y: number; width: number; height: number }
  heading: { x: number; y: number; width: number; height: number }
  title: { x: number; y: number; width: number; height: number }
}

async function collectGeometry(page: Page, descriptor: typeof sectionPages[number]): Promise<Geometry> {
  await page.goto(`/#/${descriptor.route}`, { waitUntil: 'domcontentloaded' })
  const frame = page.locator(descriptor.frame).first()
  const heading = frame.locator(descriptor.heading).first()
  const title = heading.locator('h1').first()
  await expect(frame).toBeVisible({ timeout: 15_000 })
  await expect(heading).toBeVisible({ timeout: 15_000 })
  await expect(title).toBeVisible({ timeout: 15_000 })
  // Let async data settle before reading layout. This avoids sampling the
  // pre-font/pre-grid geometry while keeping the test independent of network
  // idle (some routes intentionally keep polling or lazy-load data).
  await page.waitForTimeout(80)
  const [frameBox, headingBox, titleBox] = await Promise.all([frame.boundingBox(), heading.boundingBox(), title.boundingBox()])
  expect(frameBox).not.toBeNull()
  expect(headingBox).not.toBeNull()
  expect(titleBox).not.toBeNull()
  return {
    route: descriptor.route,
    frame: { x: frameBox!.x, y: frameBox!.y, width: frameBox!.width, height: frameBox!.height },
    heading: { x: headingBox!.x, y: headingBox!.y, width: headingBox!.width, height: headingBox!.height },
    title: { x: titleBox!.x, y: titleBox!.y, width: titleBox!.width, height: titleBox!.height },
  }
}

function maxDelta(values: number[]) {
  return Math.max(...values) - Math.min(...values)
}

test('section pages keep a shared wide frame and heading start on desktop', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'desktop frame contract')
  await page.setViewportSize({ width: 1920, height: 1080 })

  const geometry: Geometry[] = []
  for (const descriptor of sectionPages) geometry.push(await collectGeometry(page, descriptor))

  const expectedWidth = 1560
  const expectedLeft = (1920 - expectedWidth) / 2
  const expectedGutter = 34
  expect(maxDelta(geometry.map(item => item.frame.x))).toBeLessThanOrEqual(1)
  expect(maxDelta(geometry.map(item => item.frame.width))).toBeLessThanOrEqual(1)
  for (const item of geometry) {
    expect(Math.abs(item.frame.x - expectedLeft), `${item.route} frame left`).toBeLessThanOrEqual(1)
    expect(Math.abs(item.frame.width - expectedWidth), `${item.route} frame width`).toBeLessThanOrEqual(1)
    expect(Math.abs(item.heading.x - (expectedLeft + expectedGutter)), `${item.route} content gutter`).toBeLessThanOrEqual(2)
    expect(item.title.x).toBeGreaterThanOrEqual(item.frame.x)
    expect(item.title.x + item.title.width).toBeLessThanOrEqual(item.frame.x + item.frame.width + 1)
  }

  // The title block begins at the same content gutter and has the same offset
  // from its page frame, so switching routes does not make the surface jump.
  expect(maxDelta(geometry.map(item => item.title.x))).toBeLessThanOrEqual(2)
  expect(maxDelta(geometry.map(item => item.heading.y - item.frame.y))).toBeLessThanOrEqual(4)
})

test('section pages fill the mobile viewport without horizontal drift', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'mobile frame contract')
  const viewportWidth = page.viewportSize()?.width || 393

  const geometry: Geometry[] = []
  for (const descriptor of sectionPages) geometry.push(await collectGeometry(page, descriptor))

  expect(maxDelta(geometry.map(item => item.frame.x))).toBeLessThanOrEqual(1)
  expect(maxDelta(geometry.map(item => item.frame.width))).toBeLessThanOrEqual(1)
  expect(maxDelta(geometry.map(item => item.title.x))).toBeLessThanOrEqual(3)
  expect(maxDelta(geometry.map(item => item.heading.y - item.frame.y))).toBeLessThanOrEqual(4)
  for (const item of geometry) {
    expect(Math.abs(item.frame.x)).toBeLessThanOrEqual(1)
    expect(Math.abs(item.frame.width - viewportWidth)).toBeLessThanOrEqual(1)
    expect(item.title.x).toBeGreaterThanOrEqual(item.frame.x)
    expect(item.title.x + item.title.width).toBeLessThanOrEqual(item.frame.x + item.frame.width + 1)
  }

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(1)
})

test('secondary section navigation stays under the primary navigation at every desktop width', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'desktop navigation alignment contract')

  for (const width of [1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 })

    for (const route of ['modules', 'settings']) {
      await page.goto(`/#/${route}`, { waitUntil: 'domcontentloaded' })
      const primaryStart = page.locator('.desktop-nav-link').first()
      const secondaryStart = page.locator('.content-workspace-nav > a').first()
      await expect(primaryStart).toBeVisible()
      await expect(secondaryStart).toBeVisible()
      const [primaryBox, secondaryBox] = await Promise.all([
        primaryStart.boundingBox(),
        secondaryStart.boundingBox(),
      ])
      expect(primaryBox).not.toBeNull()
      expect(secondaryBox).not.toBeNull()
      expect(
        Math.abs(secondaryBox!.x - primaryBox!.x),
        `${route} secondary rail at ${width}px`,
      ).toBeLessThanOrEqual(2)
    }
  }
})
