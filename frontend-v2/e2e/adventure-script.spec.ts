import { expect, test } from './fixtures'
import { accessToken } from './support'

test('text script is reviewed, published, launched and advanced in a real game', async ({ page, request }, info) => {
  test.setTimeout(90_000)
  const title = `E2E 文字冒险 ${info.project.name}`
  const script = `# ${title}\n## 雾港\n### 抵达 {#arrival}\n浓雾笼罩码头。\nGM: 凶手藏在仓库。\n@choice 调查仓库 -> warehouse\n### 仓库 {#warehouse}\n找到线索。`
  await page.goto('/#/adventures')
  await page.locator('.adventure-header-more > summary').click()
  await page.getByRole('button', { name: '导入剧本 / 外部模组', exact: true }).click()
  await page.locator('.script-review input[type=file]').setInputFiles({ name: 'quest.md', mimeType: 'text/markdown', buffer: Buffer.from(script) })
  await page.getByTestId('script-preview').click()
  await expect(page.getByTestId('graph-name')).toHaveValue(title)
  const publish = page.getByTestId('script-publish')
  await expect(publish).toBeDisabled()
  await page.getByTestId('script-reviewed').check()
  await page.getByTestId('graph-node-description').first().fill('修改后的码头场景。')
  await expect(publish).toBeDisabled()
  await page.getByTestId('script-validate').click()
  await page.getByTestId('script-reviewed').check()
  await expect(publish).toBeEnabled()
  const geometry = await page.locator('.adventure-editor-dialog').evaluate(element => ({
    overflow: element.scrollWidth - element.clientWidth,
    right: element.getBoundingClientRect().right,
    width: window.innerWidth,
  }))
  expect(geometry.overflow).toBeLessThanOrEqual(1)
  expect(geometry.right).toBeLessThanOrEqual(geometry.width)
  await publish.click()
  await expect(page.locator('.script-review')).toHaveCount(0)
  const card = page.locator('.adventure-package-card').filter({ has: page.getByRole('heading', { name: title, exact: true }) })
  await expect(card).toBeVisible()
  await card.getByRole('link', { name: '用此冒险创建游戏' }).click()
  await expect(page).toHaveURL(/#\/create\?adventure_id=user/)
  const select = page.locator('.create-adventure-select-row select').last()
  await expect(select.locator('option:checked')).toContainText(title)
  const next = page.locator('.create-actions .primary')
  await expect(next).toBeEnabled()
  await next.click()
  await next.click()
  await expect(page.locator('.create-character-card')).toHaveCount(1)
  await next.click()
  const createResponse = page.waitForResponse(response => response.url().endsWith('/api/games/create') && response.request().method() === 'POST')
  await page.getByRole('button', { name: /创建并进入/ }).click()
  const created = await (await createResponse).json()
  expect(created.ok, JSON.stringify(created)).toBe(true)
  await expect(page).toHaveURL(/#\/play\?game=web/, { timeout: 20_000 })
  const panel = page.getByTestId('game-adventure-panel')
  await page.getByTestId('adventure-panel-toggle').click()
  await expect(panel).toContainText('修改后的码头场景。')
  await expect(panel).toContainText('凶手藏在仓库。')
  await panel.getByRole('button', { name: '确认队伍选择: 调查仓库', exact: true }).click()
  await expect(panel.getByTestId('adventure-complete-warehouse')).toBeVisible()
  const headers = { Authorization: `Bearer ${accessToken()}` }
  const projection = await (await request.get(`/api/games/${encodeURIComponent(created.game_key)}/adventure`, { headers })).json()
  expect(projection.adventure.projection.progress.active_nodes).toContain('warehouse')
})

test('module launch carries the exact installed source to game creation', async ({ page, request }) => {
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  await page.goto('/#/modules/e2e-module')
  const launch = page.getByRole('button', { name: '用此冒险创建游戏' })
  await expect(launch).toBeDisabled()
  await page.getByTestId('module-actions').getByRole('button', { name: '启用', exact: true }).click()
  try {
    await expect(launch).toBeEnabled()
    await launch.click()
    await expect(page).toHaveURL(/module_id=e2e-module.*adventure_id=plugin/)
    const selections = page.locator('.create-adventure-select-row select')
    await expect(selections.first()).toHaveValue('e2e-module')
    await expect(selections.last()).toHaveValue(JSON.stringify(['plugin', 'e2e-module', 'plugin:module_quest']))
    await expect(page.locator('.create-actions .primary')).toBeEnabled()
  } finally {
    const stopped = await request.post('/api/plugins/e2e-module/stop', { headers })
    expect(stopped.ok()).toBe(true)
  }
})
