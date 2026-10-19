import { expect, test } from './fixtures'
import type { Page } from '@playwright/test'
import { accessToken } from './support'

const GAME = 'web|e2e-room|web_bot'

async function contained(page: Page) {
  const geometry = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth - innerWidth,
    overflowing: [...document.querySelectorAll<HTMLElement>('body *')].flatMap(element => {
      const rect = element.getBoundingClientRect()
      return rect.width && rect.right > innerWidth + 1
        ? [{ tag: element.tagName, class: String(element.className), left: Math.round(rect.left), right: Math.round(rect.right), width: Math.round(rect.width) }] : []
    }).slice(0, 15),
  }))
  expect(geometry.overflow, JSON.stringify(geometry.overflowing)).toBeLessThanOrEqual(1)
}

test('restored navigation keeps content and settings reachable without the added task rail', async ({ page }, info) => {
  test.setTimeout(90_000)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(game => localStorage.setItem('currentGame', game), GAME)
  await page.goto('/#/overview')
  await expect(page.locator('.adventure-library')).toBeVisible()
  await expect(page.locator('.overview-continue-card')).toHaveCount(0)
  await expect(page.locator('.experience-rail')).toHaveCount(0)
  const navigation = page.locator((page.viewportSize()?.width || 0) <= 800 ? '.mobile-bottom-nav' : '.desktop-nav')
  await expect(navigation).toBeVisible()
  await expect(navigation.getByRole('link')).toHaveCount(5)
  for (const [name, href] of [
    ['总览', '#/overview'],
    ['角色', '#/characters'],
    ['内容', '#/library'],
  ] as const) {
    const link = navigation.getByRole('link', { name, exact: true })
    await expect(link).toBeVisible()
    await expect(link).toHaveAttribute('href', href)
  }
  await contained(page)
  await page.screenshot({ path: info.outputPath('restored-overview.png'), fullPage: true })

  await page.locator('.overview-actions').getByRole('button', { name: '创建新冒险', exact: true }).click()
  await expect(page.getByRole('combobox', { name: '世界模板', exact: true })).toBeVisible()
  await expect(page.locator('.create-rule-settings > summary')).toBeVisible()
  await expect(page.locator('.create-rule-settings')).not.toHaveAttribute('open')
  await expect(page.locator('.create-actions .primary')).toBeEnabled()
  await contained(page)
  await page.screenshot({ path: info.outputPath('restored-create.png'), fullPage: true })

  await navigation.getByRole('link', { name: '内容', exact: true }).click()
  await expect(page.getByTestId('content-library')).toBeVisible()
  await page.goto('/#/worlds')
  await expect(page.locator('.worlds-grid')).toBeVisible()
  await page.getByTestId('world-edit-lore').first().click()
  await expect(page.locator('.lore-context-bar')).toBeVisible()
  await expect(page.locator('.lore-world-rail')).toHaveCount(0)
  const world = page.getByRole('combobox', { name: '当前浏览世界', exact: true })
  await expect(world).toBeVisible()
  await world.selectOption('e2e_lore_golden')
  await expect(world).toHaveValue('e2e_lore_golden')
  await expect(page.locator('.lore-context-bar')).toContainText('Golden Lore World')
  await expect(page.locator('.lore-row').first()).toBeVisible()
  const content = page.locator('.content-workspace-nav')
  await expect(content.getByRole('link')).toHaveCount(4)
  for (const href of ['#/library', '#/lorebook', '#/modules', '#/rules']) {
    await expect(content.locator(`a[href="${href}"]`)).toBeVisible()
  }
  await contained(page)
  await page.screenshot({ path: info.outputPath('restored-lorebook.png'), fullPage: true })

  await content.locator('a[href="#/modules"]').click()
  await expect(page.getByTestId('modules-installed')).toBeVisible()
  await expect(page.locator('.content-type-filter')).toHaveCount(0)
  await contained(page)
  await page.screenshot({ path: info.outputPath('restored-modules.png'), fullPage: true })
  await page.goto('/#/creator')
  await expect(page.getByTestId('creator-workshop')).toBeVisible()
  await page.getByTestId('creator-card-adventures').click()
  await expect(page.locator('.adventure-package-card').first()).toBeVisible()
  await expect(page.locator('.adventure-studio-rail')).toHaveCount(0)
  await contained(page)
  await page.screenshot({ path: info.outputPath('restored-adventures.png'), fullPage: true })

  await navigation.getByRole('link', { name: '管理', exact: true }).click()
  await expect(page.locator('.settings-layout')).toBeVisible()
  await expect(page.locator('.settings-task-choices')).toHaveCount(0)
  await expect(page.locator('.settings-content > .n-spin-container > .n-spin-content')).not.toHaveClass(/n-spin-content--spinning/)
  await contained(page)
  await page.screenshot({ path: info.outputPath('restored-settings.png'), fullPage: true })
  // The content workspace keeps play as an explicit route; its compact content
  // chrome intentionally hides the session footer.
  await page.goto(`/#/play?game=${encodeURIComponent(GAME)}`)
  await expect.poll(() => new URLSearchParams(new URL(page.url()).hash.split('?')[1]).get('game')).toBe(GAME)
  await expect(page.locator('.composer')).toBeVisible()
  await expect(page.locator('.experience-menu-toggle')).toHaveCount(0)
  await contained(page)
  await page.screenshot({ path: info.outputPath('restored-play.png'), fullPage: true })
  expect(errors).toEqual([])
})

test('world and compact rule summary are available immediately and adventure discovery still matches defaults', async ({ page, request }, info) => {
  const catalog = await (await request.get('/api/adventures?language=zh-CN', { headers: { Authorization: `Bearer ${accessToken()}` } })).json()
  const adventure = catalog.adventures.find((item: { source_kind: string; required_runtime?: { id: string } }) => item.source_kind === 'builtin' && item.required_runtime?.id === 'core:dnd2024')
  expect(adventure).toBeTruthy()
  await page.goto('/#/create')
  await expect(page.getByRole('combobox', { name: '世界模板', exact: true })).toBeVisible()
  await expect(page.locator('.create-rule-settings > summary')).toBeVisible()
  await expect(page.locator('.create-rule-settings')).not.toHaveAttribute('open')
  await expect(page.locator('.create-stage-head h2')).toHaveText('世界')
  await page.getByRole('button', { name: /^模组冒险/ }).click()
  const select = page.locator('.create-adventure-select-row select').last()
  const option = select.locator('option').filter({ hasText: adventure.name })
  await expect(option).toHaveCount(1)
  expect(await option.getAttribute('disabled')).toBeNull()
  await select.selectOption((await option.getAttribute('value'))!)
  const next = page.locator('.create-actions .primary')
  await expect(next).toBeEnabled()
  await expect(page.locator('.create-rule-settings select')).toHaveValue('dnd2024_srd')
  await page.screenshot({ path: info.outputPath('restored-create.png'), fullPage: true })
  await next.click()
  await expect(page.locator('.create-game-settings-stage')).toBeVisible()
  await expect(page.getByRole('combobox', { name: '难度', exact: true })).toBeVisible()
})

test('restored creation preserves world material and character choices when going back', async ({ page, request }) => {
  await page.goto('/#/create')
  const worldStage = page.locator('.create-content-stage')
  const next = page.locator('.create-actions').getByRole('button', { name: /下一步/ })
  const previous = page.locator('.create-actions').getByRole('button', { name: '上一步', exact: true })
  const rules = await (await request.get('/api/rules?language=zh-CN', { headers: { Authorization: `Bearer ${accessToken()}` } })).json()
  const genericRule = rules.rules.find((rule: { ruleset_runtime?: { capabilities?: { character_builder?: string } } }) => rule.ruleset_runtime?.capabilities?.character_builder !== 'professional')
  expect(genericRule).toBeTruthy()
  await worldStage.locator('.create-rule-settings > summary').click()
  await worldStage.getByRole('combobox', { name: '规则', exact: true }).selectOption(genericRule.rule_id)
  const name = worldStage.getByPlaceholder('留空使用世界名称')
  await name.fill('UI retained adventure')
  await page.getByTestId('create-lorebook-summary').locator('summary').click()
  const material = page.getByTestId('lore-source-mode')
  await material.selectOption('__blank__')
  await next.click()
  await expect(page.locator('.create-game-settings-stage')).toBeVisible()
  await previous.click()
  await expect(name).toHaveValue('UI retained adventure')
  await expect(material).toHaveValue('__blank__')
  await next.click()
  await next.click()
  await expect(page.locator('.create-character-stage')).toBeVisible()
  await page.locator('input[type="file"][accept=".json,application/json"]').setInputFiles({
    name: 'ui-character.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({ spec: 'chara_card_v3', spec_version: '3.0', data: { name: 'UI hero', description: 'A retained character', personality: '' } })),
  })
  await expect(page.locator('.create-character-card').filter({ hasText: 'UI hero' })).toBeVisible()
  await next.click()
  await expect(page.locator('.create-confirm-stage')).toContainText('UI retained adventure')
  await expect(page.locator('.create-confirm-stage')).toContainText('新建独立世界（只有一册空白资料）')
  await expect(page.locator('.create-confirm-stage')).toContainText('UI hero')
  await previous.click()
  await expect(page.locator('.create-character-card').filter({ hasText: 'UI hero' })).toBeVisible()
})

test('settings keeps direct section links without the additional task picker', async ({ page }) => {
  test.setTimeout(60_000)
  await page.goto('/#/settings?section=appearance')
  await expect(page.locator('.background-option-card').first()).toBeVisible()
  await expect(page.locator('.settings-task-choices')).toHaveCount(0)
  await expect(page.locator('.settings-task-group')).toHaveCount(0)
  await page.goto('/#/settings?section=api')
  await expect(page.locator('.ai-management-pane')).toBeVisible()
  await expect(page.locator('.settings-content > .n-spin-container > .n-spin-content')).not.toHaveClass(/n-spin-content--spinning/)
  for (const width of [320, 390, 900, 1280, 1440]) {
    await page.setViewportSize({ width, height: 844 })
    await expect(page.locator('.provider-test-actions')).toBeVisible()
    await contained(page)
  }
  await page.goto('/#/settings?section=about')
  await expect(page.locator('.settings-pane.about')).toBeVisible()
  await expect(page.locator('.settings-content')).toContainText('DiceFrame')
  await contained(page)
})

test('restored play opens the current GM workbench from the GM drawer at narrow desktop width', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 844 })
  await page.goto(`/#/play?game=${encodeURIComponent(GAME)}`)
  await expect(page.locator('.composer')).toBeVisible()
  const gmToggle = page.getByTestId('play-gm-toggle')
  await expect(gmToggle).toHaveAttribute('aria-expanded', 'false')
  await gmToggle.click()
  await expect(gmToggle).toHaveAttribute('aria-expanded', 'true')
  const workspace = page.getByTestId('gm-workspace')
  await expect(workspace).toBeVisible()
  await expect(workspace.getByRole('tab', { name: '待办', exact: true })).toHaveAttribute('aria-selected', 'true')
  await workspace.getByRole('tab', { name: '设置', exact: true }).click()
  await expect(page.getByPlaceholder('GM 指令 / 救档操作')).toBeVisible()
  await contained(page)
})
