import { expect, test } from './fixtures'
import { accessToken } from './support'

test('enabled books and actual game books stay distinct and refresh after switching a book off', async ({ page, request }, info) => {
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  const gameKey = 'web|e2e-room|web_bot'
  const prefix = `usage-${info.project.name}`
  const usedId = `${prefix}-used`
  const unboundId = `${prefix}-unbound`
  const summary = async () => (await (await request.get(`/api/lorebooks/usage?game_key=${encodeURIComponent(gameKey)}&viewer=gm`, { headers })).json())
  const before = await summary()
  for (const [id, name] of [[usedId, '本局额外资料'], [unboundId, '已启用但未绑定的资料']]) {
    expect((await request.post('/api/lorebooks', { headers, data: { id, name, language: 'zh-CN', enabled: true } })).ok()).toBe(true)
  }
  try {
    expect((await request.post(`/api/lorebooks/${encodeURIComponent(usedId)}/bindings`, { headers, data: {
      id: `binding-${usedId}`, scope_kind: 'game', scope_id: gameKey, role: 'runtime', enabled: true,
    } })).ok()).toBe(true)
    const active = await summary()
    expect(active.library.enabled).toBe(before.library.enabled + 2)
    expect(active.game.count).toBe(before.game.count + 1)
    expect(active.game.books.map((book: { id: string }) => book.id)).not.toContain(unboundId)
    await page.addInitScript(key => localStorage.setItem('currentGame', key), gameKey)
    // Browse another world without changing what the active game uses.
    await page.goto('/#/lorebook?world=freeform_sandbox')
    const usage = page.getByTestId('lorebook-usage')
    const library = usage.locator('article').nth(0)
    const game = usage.locator('article').nth(1)
    await expect(library).toContainText(`资料库已启用 ${active.library.enabled} / ${active.library.total} 本`)
    await expect(game).toContainText(`本局使用 ${active.game.count} 本`)
    await expect(game).toContainText('E2E Adventure')
    await game.locator('summary').click()
    await expect(game).toContainText('本局额外资料')
    await expect(game).not.toContainText('已启用但未绑定的资料')
    await library.locator('summary').click()
    await expect(library).toContainText('已启用但未绑定的资料')
    await page.locator('.lore-context-row--book select').selectOption(usedId)
    await expect(page.locator('.lore-book-state')).toHaveText('资料册已启用')
    await page.getByTestId('book-actions').click()
    await page.getByRole('button', { name: '停用', exact: true }).click()
    await expect(page.locator('.lore-book-state')).toHaveText('资料册已停用')
    const disabled = await summary()
    expect(disabled.library.enabled).toBe(active.library.enabled - 1)
    expect(disabled.game.count).toBe(active.game.count - 1)
    await expect(library).toContainText(`资料库已启用 ${disabled.library.enabled} / ${disabled.library.total} 本`)
    await expect(game).toContainText(`本局使用 ${disabled.game.count} 本`)
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
    await page.getByTestId('lorebook-usage').screenshot({ path: info.outputPath('lorebook-usage.png'), scale: 'css' })
    expect(await page.evaluate(() => localStorage.getItem('currentGame'))).toBe(gameKey)
  } finally {
    for (const id of [usedId, unboundId]) expect((await request.delete(`/api/lorebooks/${encodeURIComponent(id)}`, { headers })).ok()).toBe(true)
  }
})

test('usage loading failures do not pretend zero books and can be retried', async ({ page }) => {
  let reject = true
  await page.route('**/api/lorebooks/usage?*', route => reject
    ? route.fulfill({ status: 503, json: { ok: false, error: '暂时无法读取统计' } })
    : route.continue())
  await page.goto('/#/lorebook?world=freeform_sandbox')
  const usage = page.getByTestId('lorebook-usage')
  await expect(usage).toContainText('资料册状态加载失败')
  await expect(usage).not.toContainText('本局使用 0 本')
  reject = false
  await usage.getByTestId('lorebook-usage-retry').click()
  await expect(usage.getByRole('heading', { name: /资料库已启用/ })).toBeVisible()
  await expect(usage.getByRole('heading', { name: '未选择对局', exact: true })).toBeVisible()
})
