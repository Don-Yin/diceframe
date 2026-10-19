import { expect, test } from './fixtures'

const game = 'web|e2e-room|web_bot'

async function mockCardLibrary(page: import('@playwright/test').Page) {
  await page.route(/\/api\/character-cards(?:\?|$)/, route => route.request().method() !== 'GET' ? route.continue() : route.fulfill({ json: { cards: [
    { card_id: 'journey:scout', character_name: '旅途中的侦察员', rule_id: 'freeform_fantasy', rule_name: '自由幻想', race: '人类', class: '侦察员', background: '这是一张可重复使用的角色卡；本局的变化不会自动写回。' },
    { card_id: 'journey:scholar', character_name: '旧城的学者', rule_id: 'freeform_coc', rule_name: '调查与恐怖', race: '人类', class: '学者' },
  ] } }))
}

for (const theme of ['dark', 'light']) {
  for (const width of [1366, 900, 375, 320]) {
    test(`collection pages remain readable at ${width}px in ${theme} mode`, async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'viewport and theme matrix runs once')
  await mockCardLibrary(page)
      await page.setViewportSize({ width, height: 844 })
      await page.goto('/#/overview')
      await page.evaluate(value => localStorage.setItem('diceframe_mode_v2', value), theme)
      await page.reload()
      await expect(page.locator('.game-card').first()).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
      await page.screenshot({ path: info.outputPath(`collection-overview-${width}-${theme}.png`), fullPage: true })
      if (width === 1366) await page.screenshot({ path: info.outputPath(`collection-overview-${width}-${theme}-first-screen.png`) })
      await page.goto(`/#/characters?game=${encodeURIComponent(game)}`)
      await expect(page.getByRole('tab', { name: '角色卡库', exact: true })).toHaveAttribute('aria-selected', 'true')
      await expect(page.locator('.library-character-card').first()).toBeVisible()
      await expect(page.locator('.standalone-rule-select select')).toHaveValue('freeform_fantasy')
      await expect(page.getByTestId('new-character-card')).toBeEnabled()
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
      await page.screenshot({ path: info.outputPath(`collection-card-library-${width}-${theme}.png`), fullPage: true })
      if (width === 1366) await page.screenshot({ path: info.outputPath(`collection-card-library-${width}-${theme}-first-screen.png`) })
      await page.getByRole('tab', { name: '本局角色', exact: true }).click()
      await expect(page.locator('.current-character-card').first()).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
      await page.screenshot({ path: info.outputPath(`collection-characters-${width}-${theme}.png`), fullPage: true })
      if (width === 1366) await page.screenshot({ path: info.outputPath(`collection-characters-${width}-${theme}-first-screen.png`) })
    })
  }
}

test('save selection and maintenance stay available without an automatic write', async ({ page }) => {
  const writes: string[] = []
  page.on('request', request => { if (['POST', 'PUT', 'DELETE'].includes(request.method()) && /\/api\/games/.test(request.url())) writes.push(request.url()) })
  await page.goto('/#/overview')
  await expect(page.locator('.game-card').first()).toBeVisible()
  const maintenance = page.locator('.overview-game-tools').first()
  await maintenance.locator('summary').click()
  for (const name of ['导出', '重开', '重置', '删除']) await expect(maintenance.getByRole('button', { name, exact: true })).toBeVisible()
  await page.getByTestId('overview-select-saves').click()
  const checkbox = page.locator('.game-card input[type="checkbox"]').first()
  await checkbox.check()
  await expect(page.locator('.library-heading-actions').getByRole('button', { name: /^删除\s+1$/ })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  await page.getByRole('button', { name: '全选', exact: true }).click()
  await page.getByRole('button', { name: '反选', exact: true }).click()
  await expect(checkbox).not.toBeChecked()
  await page.getByTestId('overview-exit-selection').click()
  await expect(checkbox).toHaveCount(0)
  await expect(page.locator('.overview-stats-disclosure')).toHaveAttribute('open', '')
  await expect(page.locator('.overview-stats')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  expect(writes).toEqual([])
})

test('overview omits manual joining while invite links still open the join flow', async ({ page }) => {
  await page.goto('/#/overview')
  await expect(page.locator('.game-card').first()).toBeVisible()
  await expect(page.getByRole('button', { name: '加入游戏', exact: true })).toHaveCount(0)
  const localOrigin = new URL(page.url()).origin
  await page.goto(`${localOrigin}/#/join?game=${encodeURIComponent(game)}&share=1`)
  await expect(page.getByRole('heading', { name: '创建你的角色' })).toBeVisible()
  await expect(page.getByRole('button', { name: '创建角色并进入' })).toBeVisible()
  const query = new URLSearchParams(new URL(page.url()).hash.split('?')[1])
  expect(query.get('game')).toBe(game)
  expect(query.get('share')).toBe('1')
})

test('card search and view survive switching collections without mutating characters', async ({ page }) => {
  await mockCardLibrary(page)
  const writes: string[] = []
  page.on('request', request => { if (['POST', 'PUT', 'DELETE'].includes(request.method()) && /\/api\/(?:games|character-cards)/.test(request.url())) writes.push(request.url()) })
  await page.goto(`/#/characters?game=${encodeURIComponent(game)}`)
  const search = page.locator('.character-library-toolbar input')
  await search.fill('侦察员')
  await expect(page.locator('.library-character-card:visible')).toHaveCount(1)
  await page.locator('.library-character-card:visible input[type="checkbox"]').check()
  await expect(page.getByRole('button', { name: '导出所选', exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: '批量删除', exact: true })).toBeEnabled()
  await page.locator('.character-view-switch button').nth(1).click()
  await page.getByRole('tab', { name: '本局角色', exact: true }).click()
  await expect(page.locator('.current-character-card').first()).toBeVisible()
  await page.getByRole('tab', { name: '角色卡库', exact: true }).click()
  await expect(search).toHaveValue('侦察员')
  await expect(page.locator('.character-library-grid')).toHaveClass(/view-list/)
  await expect(page.locator('.library-character-card:visible')).toHaveCount(1)
  await page.getByRole('button', { name: '导入酒馆卡', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByRole('dialog').locator('input[value="character_card"]')).toBeVisible()
  expect(writes).toEqual([])
})

test('a missing game does not hide the reusable card library', async ({ page }) => {
  await mockCardLibrary(page)
  await page.goto('/#/characters?game=web%7Cdoes-not-exist%7Cgm&pane=current')
  await expect(page.locator('#character-current-panel')).toBeVisible()
  await page.getByRole('tab', { name: '角色卡库', exact: true }).click()
  await expect(page.locator('.library-character-card')).toHaveCount(2)
  await expect(page.locator('.library-character-card').first()).toBeVisible()
  await expect(page.getByTestId('new-character-card')).toBeDisabled()
})

test('a professional live character still opens its ruleset character center', async ({ page }) => {
  await page.goto('/#/characters?game=web%7Ce2e-dnd2024%7Cweb_bot&pane=current')
  const character = page.locator('.current-character-card').first()
  await expect(character).toContainText('新手守护者')
  await character.getByRole('button', { name: '高级角色中心', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '高级角色中心' })).toBeVisible()
  await expect(page.locator('.professional-character-center')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
})
