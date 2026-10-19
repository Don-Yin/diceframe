import { expect, test } from './fixtures'

const game = 'web|e2e-room|web_bot'
const pages = [
  ['play', `/#/play?game=${encodeURIComponent(game)}`, '[data-testid="timeline"]'],
  ['modules', '/#/modules', '[data-testid="modules-installed"]'],
  ['module-detail', '/#/modules/e2e-module', '[data-testid="module-content"]'],
  ['rules', '/#/rules', '.rule-card'],
  ['settings', '/#/settings', '.settings-nav'],
  ['plugins', '/#/plugins', '.plugin-surface-tabs'],
  ['memory', '/#/memory', '.memory-page'],
  ['logs', '/#/logs', '.logs-page'],
  ['join', `/#/join?game=${encodeURIComponent(game)}&share=1`, '.join-progress'],
  ['peer', '/#/peer', '.peer-flow-steps'],
] as const

for (const theme of ['dark', 'light']) {
  for (const width of [1366, 900, 375, 320]) {
    test(`remaining journeys fit ${width}px in ${theme} mode`, async ({ page }, info) => {
      test.skip(info.project.name !== 'desktop', 'independent viewport matrix runs once')
      test.setTimeout(120_000)
      await page.setViewportSize({ width, height: 900 })
      await page.addInitScript(({ game, theme }) => {
        localStorage.setItem('currentGame', game)
        localStorage.setItem('diceframe_mode_v2', theme)
      }, { game, theme })
      for (const [name, url, selector] of pages) {
        await page.goto(url)
        await expect(page.locator(selector).first()).toBeVisible()
        await expect(page.locator('.n-spin-body:visible')).toHaveCount(0)
        const excess = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
        expect(excess, `${name} ${width}px ${theme} horizontal overflow`).toBeLessThanOrEqual(1)
        if (name === 'play') {
          await expect(page.getByTestId('play-gm-toggle')).toHaveAttribute('aria-expanded', 'false')
          await expect(page.locator('.composer')).toBeVisible()
          const geometry = await page.getByTestId('timeline').boundingBox()
          expect(geometry?.height || 0).toBeGreaterThan(260)
          if (width >= 900) await expect(page.getByTestId('play-character-dock')).toBeVisible()
          else await expect(page.getByTestId('play-quick-status')).toBeVisible()
        }
        if (name === 'join') {
          await expect(page.locator('.player-sheet-form, .professional-join-form').first()).toBeVisible()
          await expect(page.locator('.join-avatar-details')).not.toHaveAttribute('open')
        }
        await page.screenshot({ path: info.outputPath(`final-${name}-${width}-${theme}.png`), fullPage: true })
        if (width === 1366) await page.screenshot({ path: info.outputPath(`final-${name}-${width}-${theme}-first-screen.png`) })
      }
    })
  }
}

test('play tools remain reachable and keep the GM and character surfaces independent', async ({ page }) => {
  await page.goto(`/#/play?game=${encodeURIComponent(game)}`)
  await expect(page.getByTestId('timeline')).toBeVisible()
  const tools = page.getByTestId('play-tools-toggle')
  await tools.click()
  const panel = page.getByTestId('play-tools-panel')
  await expect(panel).toBeVisible()
  for (const name of ['共享角色卡库', '场景画廊', '帮助', '刷新']) {
    await expect(panel.getByRole('button', { name, exact: true })).toBeVisible()
  }
  const compact = page.viewportSize()!.width <= 800
  for (const name of ['角色', '场景地图', '队伍']) {
    await expect(panel.getByRole('button', { name, exact: true })).toHaveCount(compact ? 1 : 0)
  }
  await panel.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(tools).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByTestId('timeline')).toBeVisible()
  await tools.click()
  await page.keyboard.press('Escape')
  await expect(tools).toBeFocused()
  await page.getByTestId('play-gm-toggle').click()
  await expect(page.getByTestId('gm-workspace')).toBeVisible()
  await expect(page.getByTestId('play-tools-panel')).toHaveCount(0)
})

test('management deep links and advanced disclosures preserve their original task controls', async ({ page }) => {
  await page.goto('/#/settings?section=security')
  await expect(page.locator('.settings-status-disclosure')).not.toHaveAttribute('open')
  await page.locator('.settings-status-disclosure > summary').click()
  await expect(page.locator('.system-status-grid')).toBeVisible()
  const navToggle = page.locator('.settings-nav-toggle')
  if (await navToggle.isVisible()) await navToggle.click()
  await expect(page.locator('.settings-nav .nav-item.active')).toContainText('安全')
  expect(await page.locator('.settings-nav .nav-item:not(.settings-nav-toggle)').count()).toBeGreaterThanOrEqual(10)
  await page.locator('.settings-nav .nav-item').filter({ hasText: '外观主题' }).click()
  await expect(page).toHaveURL(/section=appearance/)
  await expect(page.locator('.settings-nav .nav-item.active')).toContainText('外观')
  await page.goto('/#/modules/e2e-module')
  const metadata = page.getByTestId('module-metadata')
  await expect(metadata).not.toHaveAttribute('open')
  await metadata.locator('summary').click()
  await expect(metadata.getByText('e2e-module', { exact: true })).toBeVisible()
  await expect(page.getByTestId('module-actions').getByRole('button', { name: '卸载' })).toBeVisible()
})

test('package sections remain accessible without duplicate links and optional portraits keep their full editor', async ({ page }) => {
  await page.goto('/#/modules')
  await expect(page.locator('.content-workspace-nav a').first()).toHaveText('内容库')
  await expect(page.locator('.modules-heading .content-page-heading-actions a')).toHaveCount(1)
  await expect(page.locator('.modules-return-link')).toContainText('返回内容库')
  await page.locator('#modules-online h2').scrollIntoViewIfNeeded()
  await expect(page).toHaveURL(/#\/modules$/)
  await expect(page.locator('#modules-online h2')).toBeInViewport()
  await page.goto(`/#/join?game=${encodeURIComponent(game)}&share=1`)
  const portrait = page.locator('.join-avatar-details')
  await expect(portrait).not.toHaveAttribute('open')
  await portrait.locator('summary').click()
  await expect(portrait.getByRole('button', { name: '上传自定义头像' })).toBeVisible()
  await portrait.locator('summary').click()
  await expect(portrait).not.toHaveAttribute('open')
})
