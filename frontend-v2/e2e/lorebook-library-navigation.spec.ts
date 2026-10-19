import { expect, test } from './fixtures'
import { accessToken } from './support'

const WORLD_ID = 'freeform_sandbox'

test('content library opens a canonical non-primary book, entry, and preserves manual book changes', async ({ page, request }, testInfo) => {
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  const bookId = `library-navigation-${testInfo.project.name}-${testInfo.workerIndex}`
  const bookEntriesPath = `/api/lorebooks/${encodeURIComponent(bookId)}/entries`
  const entryIds = [`${bookId}:entry:one`, `${bookId}:entry:two`]
  let bookCreated = false
  let bookDeleted = false

  const create = await request.post('/api/lorebooks', {
    headers,
    data: { id: bookId, name: `Library navigation ${testInfo.project.name}`, language: 'zh-CN', enabled: true },
  })
  expect(create.ok(), await create.text()).toBe(true)
  bookCreated = true
  const binding = await request.post(`/api/lorebooks/${encodeURIComponent(bookId)}/bindings`, {
    headers,
    data: { id: `${bookId}:world:${WORLD_ID}`, scope_kind: 'world', scope_id: WORLD_ID, role: 'runtime', enabled: true },
  })
  expect(binding.ok(), await binding.text()).toBe(true)
  for (const [index, id] of entryIds.entries()) {
    const response = await request.post(`/api/lorebooks/${encodeURIComponent(bookId)}/entries`, {
      headers,
      data: { id, name: `Library entry ${index + 1}`, type: 'npc', content: `Canonical entry ${index + 1}`, keywords: [`library-entry-${index + 1}`], enabled: true },
    })
    expect(response.ok(), await response.text()).toBe(true)
  }

  try {
    await page.goto('/#/library')
    const card = page.getByTestId('library-lorebook').filter({ hasText: `Library navigation ${testInfo.project.name}` })
    await expect(card).toBeVisible()
    const open = card.getByRole('link', { name: '打开', exact: true })
    await expect(open).toHaveAttribute('data-book-id', bookId)
    await open.click()
    await expect(page).toHaveURL(new RegExp(`#\\/lorebook\\?world=${WORLD_ID}&book=${encodeURIComponent(bookId)}`))
    await expect(page.locator('.lore-context-row--book select')).toHaveValue(bookId)
    await expect(page.locator('.lore-row', { hasText: 'Library entry 1' })).toBeVisible()
    await expect(page.locator('.lore-row', { hasText: 'Library entry 2' })).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('library-open-canonical-book.png'), fullPage: true })

    await page.goto(`/#/lorebook?world=${WORLD_ID}&book=${encodeURIComponent(bookId)}&entry=${encodeURIComponent(entryIds[1]!)}`)
    await expect(page.locator('.lore-row.selected')).toContainText('Library entry 2')
    await expect(page.locator('.lore-context-row--book select')).toHaveValue(bookId)

    // Hold the old-book response while the user switches to the primary book;
    // releasing it afterwards proves a late request cannot reclaim selection.
    let releaseOldBook!: () => void
    const oldBookResponse = new Promise<void>(resolve => { releaseOldBook = resolve })
    await page.route(`**${bookEntriesPath}`, async route => {
      const response = await route.fetch()
      await oldBookResponse
      await route.fulfill({ response })
    }, { times: 1 })
    await page.locator('.lore-context-row--book select').selectOption(`world:${WORLD_ID}`)
    const oldBookRequest = page.waitForRequest(request => new URL(request.url()).pathname.endsWith(bookEntriesPath))
    await page.locator('.lore-context-row--book select').selectOption(bookId)
    await oldBookRequest
    await page.locator('.lore-context-row--book select').selectOption(`world:${WORLD_ID}`)
    releaseOldBook()
    await expect(page.locator('.lore-context-row--book select')).toHaveValue(`world:${WORLD_ID}`)
    await expect(page.locator('.lore-context-row--book .lore-book-meta')).toContainText('主资料册')

    const bookMenu = page.getByTestId('book-actions').locator('..')
    await bookMenu.locator('summary').click()
    await expect(bookMenu.getByRole('button', { name: '删除资料册', exact: true })).toHaveCount(0)
    await bookMenu.locator('summary').click()
    await page.locator('.lore-context-row--book select').selectOption(bookId)
    await expect(page.locator('.lore-context-row--book select')).toHaveValue(bookId)
    await bookMenu.locator('summary').click()
    await bookMenu.getByRole('button', { name: '删除资料册', exact: true }).click()
    await page.getByRole('button', { name: '删除资料册', exact: true }).click()
    // With one scoped book left, the primary uses a static title instead of
    // a redundant dropdown. Its protection must still be enforced in the UI.
    await expect(page.locator('.lore-context-row--book .lore-book-meta')).toContainText('主资料册')
    await bookMenu.locator('summary').click()
    await expect(bookMenu.getByRole('button', { name: '删除资料册', exact: true })).toHaveCount(0)
    bookDeleted = true
  } finally {
    if (bookCreated && !bookDeleted) {
      const removed = await request.delete(`/api/lorebooks/${encodeURIComponent(bookId)}`, { headers })
      expect(removed.ok(), await removed.text()).toBe(true)
    }
  }
})
