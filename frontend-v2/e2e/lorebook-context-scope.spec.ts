import { expect, test } from './fixtures'

test('a linked book keeps world and language choices scoped across navigation and refresh', async ({ page }, info) => {
  const books = [
    { id: 'world:w1', name: '第一世界主册', scope: 'world', language: 'zh-CN', primary: true },
    { id: 'side:w1', name: '第一世界人物志', scope: 'world', language: 'zh-CN' },
    { id: 'world:w2', name: '第二世界主册', scope: 'world', language: 'zh-CN', primary: true },
    { id: 'world:w1-en', name: 'English primary book', scope: 'world', language: 'en', primary: true },
    { id: 'side:w1-en', name: 'English characters', scope: 'world', language: 'en' },
    { id: 'global:zh', name: '中文通用资料', scope: 'global', language: 'zh-CN' },
    { id: 'global:en', name: 'English reference', scope: 'global', language: 'en' },
  ]
  await page.route('**/api/worlds', route => route.fulfill({ json: { worlds: [
    { id: 'w1', name: '第一世界', language: 'zh-CN' },
    { id: 'w2', name: '第二世界', language: 'zh-CN' },
    { id: 'w1-en', name: 'English World', language: 'en' },
  ] } }))
  await page.route('**/api/lorebooks?*', route => {
    const query = new URL(route.request().url()).searchParams
    const world = query.get('world_id') || ''
    return route.fulfill({ json: { books: query.get('scope') === 'all' ? books
      : books.filter(book => book.scope === 'global' || book.id === `world:${world}` || book.id === `side:${world}`) } })
  })
  await page.route('**/api/lorebooks/*/entries', route => route.fulfill({ json: { entries: [] } }))
  await page.goto('/#/lorebook?world=w1&book=side:w1&entry=old-entry')
  const book = page.locator('.lore-context-row--book select')
  const world = page.locator('.lore-context-row--world select')
  await expect(book).toHaveValue('side:w1')
  await expect(book.locator('option')).toHaveCount(3)
  await expect(book).not.toContainText('English')
  await expect(book).not.toContainText('第二世界')
  await world.selectOption('w2')
  await expect(book).toHaveValue('world:w2')
  await expect(book.locator('option')).toHaveCount(2)
  await expect(page).toHaveURL(/world=w2(?:&|$)/)
  expect(new URLSearchParams(new URL(page.url()).hash.split('?')[1]).has('book')).toBe(false)
  expect(new URLSearchParams(new URL(page.url()).hash.split('?')[1]).has('entry')).toBe(false)
  await page.reload()
  await expect(world).toHaveValue('w2')
  await expect(book).toHaveValue('world:w2')
  await page.locator('.lore-language-filter select').selectOption('en')
  await expect(world).toHaveValue('w1-en')
  await expect(book).toHaveValue('world:w1-en')
  await expect(book.locator('option')).toHaveCount(3)
  await expect(book).not.toContainText('中文通用')
  await expect(page).toHaveURL(/world=w1-en(?:&|$)/)
  await page.reload()
  await expect(page.locator('.lore-language-filter select')).toHaveValue('en')
  await expect(book).toHaveValue('world:w1-en')
  await page.screenshot({ path: info.outputPath('world-books-follow-language.png'), scale: 'css' })
})
