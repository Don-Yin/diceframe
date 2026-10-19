import { readFileSync } from 'node:fs'
import { expect, test } from './fixtures'
import { accessToken } from './support'

test('an orphan primary book opens from the library and remains editable without changing worlds', async ({ page, request }, testInfo) => {
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  const worldId = `custom_book_world_orphan_${testInfo.project.name}`
  const bookId = `world:${worldId}`
  const bookName = `Orphan book ${testInfo.project.name}`
  const entriesPath = `/api/lorebooks/${encodeURIComponent(bookId)}/entries`
  const worldsBefore = (await (await request.get('/api/worlds', { headers })).json()).worlds
    .map((world: { id: string }) => world.id).sort()
  expect(worldsBefore).not.toContain(worldId)

  const created = await request.post('/api/lorebooks', {
    headers, data: { id: bookId, name: bookName, source_kind: 'world', source_id: worldId, language: 'zh-CN' },
  })
  expect(created.ok(), await created.text()).toBe(true)
  const bound = await request.post(`/api/lorebooks/${encodeURIComponent(bookId)}/bindings`, {
    headers,
    data: { id: `${bookId}:binding`, scope_kind: 'world', scope_id: worldId, role: 'primary', enabled: true },
  })
  expect(bound.ok(), await bound.text()).toBe(true)
  const bindingsBefore = await (await request.get(`/api/lorebooks/${encodeURIComponent(bookId)}/bindings`, { headers })).json()

  await page.goto('/#/library')
  const card = page.getByTestId('library-lorebook').filter({ hasText: bookName })
  const open = card.getByRole('link', { name: '打开', exact: true })
  const target = new URL((await open.getAttribute('href'))!.slice(1), 'http://localhost')
  expect(target.searchParams.get('book')).toBe(bookId)
  expect(target.searchParams.has('world')).toBe(false)
  await open.click()
  const worldSelect = page.locator('.lore-context-row--world select')
  const bookSelect = page.locator('.lore-context-row--book select')
  await expect(worldSelect).toHaveValue('')
  await expect(worldSelect.locator('option:checked')).toHaveText('独立资料册浏览')
  await expect(bookSelect).toHaveValue(bookId)
  await expect(page.locator('.lore-context-warning')).toContainText('关联世界不可用')
  await expect(page.getByRole('heading', { name: '暂无资料册条目', exact: true })).toBeVisible()
  await expect(page.locator('.error-banner')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '新增条目', exact: true })).toBeEnabled()
  await page.screenshot({ path: testInfo.outputPath('orphan-empty-book.png'), fullPage: true })

  await page.getByRole('button', { name: '新增条目', exact: true }).click()
  const newEntry = page.getByRole('dialog', { name: '新增资料条目', exact: true })
  await newEntry.getByLabel('名称', { exact: true }).fill('Recovered orphan entry')
  await newEntry.getByLabel('内容', { exact: true }).fill('Created through the canonical book.')
  const saved = page.waitForResponse(response => new URL(response.url()).pathname === entriesPath && response.request().method() === 'POST')
  await newEntry.getByRole('button', { name: '保存', exact: true }).click()
  expect((await saved).ok()).toBe(true)
  const row = page.locator('.lore-row', { hasText: 'Recovered orphan entry' })
  await expect(row).toBeVisible()
  await expect(bookSelect).toHaveValue(bookId)
  await expect(worldSelect).toHaveValue('')
  const entries = await (await request.get(entriesPath, { headers })).json()
  expect(entries.entries).toHaveLength(1)
  const entryId = entries.entries[0].id
  expect(entries.entries[0].book_id).toBe(bookId)
  expect(entries.entries[0].world_id).toBeNull()

  await row.getByRole('button', { name: '编辑', exact: true }).click()
  const editor = page.getByTestId('lore-inline-editor')
  await editor.getByLabel('内容', { exact: true }).fill('Edited independently.')
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  await expect(row).toContainText('Edited independently.')
  await expect(bookSelect).toHaveValue(bookId)

  // Cached URLs and in-place query changes must keep the same canonical book.
  await page.evaluate(({ bookId }) => { location.hash = `/lorebook?world=freeform_sandbox&book=${encodeURIComponent(bookId)}` }, { bookId })
  await expect(worldSelect).toHaveValue('freeform_sandbox')
  await expect(bookSelect).toHaveValue(bookId)
  await expect(row).toBeVisible()
  await page.evaluate(({ worldId, bookId, entryId }) => {
    location.hash = `/lorebook?world=${worldId}&book=${encodeURIComponent(bookId)}&entry=${encodeURIComponent(entryId)}`
  }, { worldId, bookId, entryId })
  await expect(worldSelect).toHaveValue('')
  await expect(bookSelect).toHaveValue(bookId)
  await expect(page.locator('.lore-row.selected')).toContainText('Recovered orphan entry')
  await expect(page.locator('.lore-context-warning')).toContainText(worldId)
  await expect(page.locator('.error-banner')).toHaveCount(0)
  await page.reload()
  await expect(bookSelect).toHaveValue(bookId)
  await expect(page.locator('.lore-row.selected')).toContainText('Recovered orphan entry')

  const bookMenu = page.getByTestId('book-actions').locator('..')
  await bookMenu.locator('summary').click()
  await expect(bookMenu.getByRole('button', { name: '删除资料册', exact: true })).toHaveCount(0)
  const downloaded = page.waitForEvent('download')
  await bookMenu.getByRole('button', { name: '导出', exact: true }).click()
  const downloadPath = await (await downloaded).path()
  expect(JSON.parse(readFileSync(downloadPath!, 'utf8')).ok).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('orphan-cached-link-entry.png'), fullPage: true })

  const worldsAfter = (await (await request.get('/api/worlds', { headers })).json()).worlds
    .map((world: { id: string }) => world.id).sort()
  expect(worldsAfter).toEqual(worldsBefore)
  expect(await (await request.get(`/api/lorebooks/${encodeURIComponent(bookId)}/bindings`, { headers })).json()).toEqual(bindingsBefore)
  const protectedDelete = await request.delete(`/api/lorebooks/${encodeURIComponent(bookId)}`, { headers })
  expect(protectedDelete.status()).toBe(409)

  await page.goto(`/#/lorebook?world=${worldId}`)
  await expect(page.locator('.error-banner')).toContainText(worldId)
  await expect(worldSelect).toHaveValue('')
  await expect(page.locator('.lore-row')).toHaveCount(0)
  // The isolated E2E instance owns this primary fixture and is discarded in full.
})
