import { expect, test } from './fixtures'
import { accessToken } from './support'

const token = accessToken

test('settings status summary stays structured and destructive confirmations are explicit', async ({ page }) => {
  await page.addInitScript(value => localStorage.setItem('trpg_access_token', value), token())

  await page.goto('/#/settings')
  await expect(page.locator('.system-status-grid')).toBeVisible()
  const statusCards = page.locator('.system-status-card')
  await expect(statusCards.first()).toBeVisible()
  const summaries = await statusCards.evaluateAll(elements => elements.map(element => ({
    label: element.querySelector('.system-status-head > span')?.textContent?.trim() ?? '',
    value: element.querySelector('.system-status-tag')?.textContent?.trim() ?? '',
    detail: element.querySelector('p')?.textContent?.trim() ?? '',
  })))
  expect(summaries.length).toBeGreaterThan(0)
  for (const summary of summaries) {
    expect(summary.label).not.toBe('')
    expect(summary.value).not.toBe('')
    expect(summary.detail).not.toBe('')
  }

  await page.goto('/')
  await page.getByRole('button', { name: '删除' }).first().click()
  await expect(page.getByText('删除存档').first()).toBeVisible()
  await expect(page.getByRole('button', { name: '删除存档' })).toBeVisible()
  await page.getByRole('button', { name: '取消', exact: true }).click()
})

test('settings status grid stays within viewport for German locale', async ({ page }) => {
  await page.addInitScript(value => localStorage.setItem('trpg_access_token', value), token())
  await page.addInitScript(() => localStorage.setItem('diceframe_locale', 'de'))
  await page.setViewportSize({ width: 1280, height: 1024 })
  await page.goto('/#/settings')
  const grid = page.locator('.system-status-grid')
  await expect(grid).toBeVisible()
  const overflow = await grid.evaluate(el => ({
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
  }))
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1)
  // 德语界面回退英文：状态卡标题不应出现中文
  const labels = await page.locator('.system-status-head > span').allTextContents()
  expect(labels.length).toBeGreaterThan(0)
  for (const label of labels) {
    expect(label).not.toMatch(/[一-鿿]/)
  }
})
test('rules page exposes structured editing for copied rules', async ({ page }) => {
  await page.addInitScript(value => localStorage.setItem('trpg_access_token', value), token())
  await page.goto('/#/rules')
  await page.getByRole('button', { name: '复制并编辑' }).first().click()
  await expect(page.getByRole('heading', { name: '复制并编辑规则' })).toBeVisible()
  await expect(page.getByLabel('规则 ID')).toBeVisible()
  await expect(page.getByLabel('规则名称')).toBeVisible()
  await expect(page.locator('.rule-editor-section').filter({ hasText: '属性' })).toBeVisible()
  await expect(page.getByText('高级 JSON')).toBeVisible()
  await page.getByRole('button', { name: '取消' }).click()
})
test('provider controls and the add action remain usable', async ({ page }) => {
  await page.goto('/#/settings?section=api')
  const testSection = page.locator('.provider-test-section')
  await expect(testSection).toBeVisible()
  await expect(testSection.locator('.provider-field .n-input')).toBeVisible()
  await expect(testSection.locator('.provider-field .n-select')).toBeVisible()
  await expect(testSection.locator('.provider-test-actions .n-button').first()).toBeVisible()

  const addProvider = page.locator('.provider-library-footer button')
  await expect(addProvider).toBeVisible()
  await expect(addProvider).toBeEnabled()
  const providerItems = page.locator('.provider-list-item')
  const providerCount = await providerItems.count()
  await addProvider.click()
  await expect(providerItems).toHaveCount(providerCount + 1)
})

test('model routing pane keeps provider and model assignment reactive after extraction', async ({ page }) => {
  await page.goto('/#/settings?section=models')
  const pane = page.locator('.model-routing-pane')
  await expect(pane).toBeVisible()
  await expect(pane.locator('.model-role-card-main')).toBeVisible()

  const mainProvider = pane.locator('.model-role-card-main > label select').nth(0)
  const mainModel = pane.locator('.model-role-card-main > label select').nth(1)
  const providerOptions = await mainProvider.locator('option').count()
  expect(providerOptions).toBeGreaterThan(1)
  await mainProvider.selectOption({ index: 1 })

  await expect(mainModel).toBeEnabled()
  await expect(mainModel).not.toHaveValue('')
  await expect(pane.locator('.model-role-card-embedding')).toBeVisible()
})
