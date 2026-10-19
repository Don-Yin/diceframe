import { expect, test } from './fixtures'
import { prepareAuthenticatedPage } from './support'
import type { Page } from '@playwright/test'

type ThemeSnapshot = {
  backgroundColor: string
  color: string
  surfaceToken: string
}

function relativeLuminance(color: string): number {
  const rgb = color.match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i)
  const srgb = color.match(/color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)/i)
  const channels = rgb
    ? rgb.slice(1, 4).map(Number)
    : srgb
      ? srgb.slice(1, 4).map(value => Number(value) * 255)
      : undefined
  if (!channels || channels.length !== 3) throw new Error(`Expected rgb color, got ${color}`)
  const linear = channels.map(channel => {
    const normalized = channel / 255
    return normalized <= .03928
      ? normalized / 12.92
      : ((normalized + .055) / 1.055) ** 2.4
  })
  return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2]
}

async function themeSnapshot(page: Page, selector: string): Promise<ThemeSnapshot> {
  return page.locator(selector).evaluate(element => {
    const style = getComputedStyle(element)
    const root = getComputedStyle(document.documentElement)
    const resolveToken = (token: string) => {
      const probe = document.createElement('span')
      probe.style.color = token
      document.body.appendChild(probe)
      const resolved = getComputedStyle(probe).color
      probe.remove()
      return resolved
    }
    return {
      backgroundColor: style.backgroundColor,
      color: style.color,
      surfaceToken: resolveToken(root.getPropertyValue('--df-surface-1').trim()),
    }
  })
}

test('module surfaces follow the active semantic theme in dark and light mode', async ({ page, request }, testInfo) => {
  await prepareAuthenticatedPage(page, request)
  await page.route('**/api/modules/marketplace*', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      ok: true,
      modules: [{
        id: 'e2e-online-module',
        name: 'E2E Online Module',
        version: '1.0.0',
        latest_version: '1.0.0',
        description: 'Theme contract fixture',
        content_profile: 'content-pack',
        content_delivery_mode: 'catalog',
        adventure_count: 0,
        ruleset_targets: ['freeform'],
        languages: ['en'],
        tags: ['e2e'],
        trust_level: 'verified',
        distribution: 'hub',
        repository_url: '',
        release_url: '',
        stars: 0,
        installed: false,
        installed_version: '',
        update_available: false,
        installable: true,
        verification_error: '',
        needs_core_update: false,
        min_app_version: '',
      }],
      total: 1,
    }),
  }))
  await page.goto('/#/modules')
  for (const light of [false, true]) {
    await page.evaluate(value => localStorage.setItem('diceframe_mode_v2', value ? 'light' : 'dark'), light)
    await page.reload()
    await expect(page.getByTestId('modules-installed')).toBeVisible()
    const card = page.locator('.modules-page .module-card').first()
    await expect(card).toBeVisible()
    const onlineCard = page.getByTestId('modules-market-e2e-online-module')
    await expect(onlineCard).toBeVisible()
    const installedCard = page.locator('.modules-page a.module-card').first()
    await expect(installedCard).toBeVisible()
    await expect(installedCard).toHaveCSS('text-decoration-line', 'none')

    const snapshot = await themeSnapshot(page, '[data-testid="modules-installed"] .module-card')
    expect(snapshot.backgroundColor, `module card surface in ${light ? 'light' : 'dark'} mode`)
      .toBe(snapshot.surfaceToken)

    const background = relativeLuminance(snapshot.backgroundColor)
    const foreground = relativeLuminance(snapshot.color)
    if (light) {
      expect(background, 'light mode module surface should remain light').toBeGreaterThan(.65)
      expect(foreground, 'light mode module text should remain readable').toBeLessThan(background)
    } else {
      expect(background, 'dark mode module surface should remain dark').toBeLessThan(.35)
      expect(foreground, 'dark mode module text should remain readable').toBeGreaterThan(background)
    }

    const onlineSnapshot = await themeSnapshot(page, '[data-testid="modules-market-e2e-online-module"]')
    expect(onlineSnapshot.backgroundColor, `online module surface in ${light ? 'light' : 'dark'} mode`)
      .toBe(onlineSnapshot.surfaceToken)
    await page.screenshot({ path: testInfo.outputPath(`modules-${light ? 'light' : 'dark'}.png`), fullPage: true })
  }

  await page.setViewportSize({ width: 390, height: 844 })
  await page.reload()
  const marketInput = page.locator('.module-market-search input')
  await expect(marketInput).toBeVisible()
  const marketInputHeight = await marketInput.evaluate(element => element.getBoundingClientRect().height)
  expect(marketInputHeight).toBeGreaterThanOrEqual(36)
  expect(marketInputHeight).toBeLessThanOrEqual(48)
})

test('adventure launch action link has button presentation and stable card geometry', async ({ page, request }, testInfo) => {
  await prepareAuthenticatedPage(page, request)
  await page.goto('/#/adventures')
  for (const light of [false, true]) {
    await page.evaluate(value => localStorage.setItem('diceframe_mode_v2', value ? 'light' : 'dark'), light)
    await page.reload()
    const card = page.locator('.adventure-package-card').filter({ has: page.getByRole('link', { name: '用此冒险创建游戏', exact: true }) }).first()
    await expect(card).toBeVisible()
    const action = card.getByRole('link', { name: '用此冒险创建游戏', exact: true })
    await expect(action).toBeVisible()

    const geometry = await action.evaluate(element => {
      const style = getComputedStyle(element)
      const bounds = element.getBoundingClientRect()
      return {
        display: style.display,
        alignItems: style.alignItems,
        justifyContent: style.justifyContent,
        textDecorationLine: style.textDecorationLine,
        minHeight: Number.parseFloat(style.minHeight),
        height: bounds.height,
        width: bounds.width,
        textOverflow: element.scrollWidth - element.clientWidth,
        backgroundImage: style.backgroundImage,
        borderTopWidth: Number.parseFloat(style.borderTopWidth),
        borderTopLeftRadius: Number.parseFloat(style.borderTopLeftRadius),
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      }
    })

    // Grid items blockify inline-flex to flex in their computed style.
    expect(['flex', 'inline-flex']).toContain(geometry.display)
    expect(geometry.alignItems).toBe('center')
    expect(geometry.justifyContent).toBe('center')
    expect(geometry.textDecorationLine).toBe('none')
    expect(geometry.minHeight).toBeGreaterThanOrEqual(36)
    expect(geometry.height).toBeGreaterThanOrEqual(34)
    expect(geometry.width).toBeGreaterThan(80)
    expect(geometry.textOverflow).toBeLessThanOrEqual(1)
    expect(geometry.backgroundImage).not.toBe('none')
    expect(geometry.borderTopWidth).toBeGreaterThan(0)
    expect(geometry.borderTopLeftRadius).toBeGreaterThan(0)
    expect(geometry.overflow).toBe(0)
    await page.screenshot({ path: testInfo.outputPath(`adventures-${light ? 'light' : 'dark'}.png`), fullPage: true })
  }
})
