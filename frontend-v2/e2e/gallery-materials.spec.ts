import { expect, test } from './fixtures'
import { accessToken } from './support'

test('every bundled gallery world reaches its local lorebook, including the blank sandbox', async ({ page, request }) => {
  const headers = { Authorization: `Bearer ${accessToken()}` }
  const templates = (await (await request.get('/api/world-templates?language=zh-CN', { headers })).json()).templates
    .filter((world: { source: string; game_scoped?: boolean }) => world.source === 'builtin' && !world.game_scoped)
  const worlds = (await (await request.get('/api/worlds', { headers })).json()).worlds
  const persistedIds = worlds.map((world: { id: string }) => world.id)
  expect(templates.map((world: { world_id: string }) => world.world_id)).toContain('freeform_sandbox')
  for (const template of templates) {
    expect(persistedIds, `${template.world_id} must be initialized even without starter entries`).toContain(template.world_id)
  }
  for (const template of templates) {
    await page.goto('/#/worlds')
    const card = page.locator(`.world-card[data-world-id="${template.world_id}"]`)
    await card.getByTestId('world-edit-lore').click()
    await expect(page).toHaveURL(new RegExp(`#/lorebook\\?world=${template.world_id}`))
    await expect(page.locator('.lore-context-row--world select')).toHaveValue(template.world_id)
    await expect(page.locator('.error-banner')).toHaveCount(0)
    await expect(page.locator('.lore-book-static, .lore-context-row--book select')).toHaveCount(1)
  }
  const sandbox = (await (await request.get('/api/lorebooks?world_id=freeform_sandbox', { headers })).json()).books
  const book = sandbox.find((entry: { id: string }) => entry.id === 'world:freeform_sandbox')
  expect(book).toMatchObject({ primary: true, entry_count: 0 })
})

test('catalog world offers an explicit editable copy without importing or changing its source', async ({ page, request }) => {
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  expect((await request.post('/api/plugins/e2e-module/start', { headers })).ok()).toBe(true)
  const gameKey = 'web|e2e-room|web_bot'
  await page.addInitScript(key => localStorage.setItem('currentGame', key), gameKey)
  let clonedId = ''
  try {
    const idsBefore = (await (await request.get('/api/worlds', { headers })).json()).worlds.map((world: { id: string }) => world.id)
    expect(idsBefore).not.toContain('resource_world')
    await page.goto('/#/worlds')
    await page.locator('.world-card[data-world-id="resource_world"]').getByTestId('world-edit-lore').click()
    await expect(page).toHaveURL(/#\/worlds$/)
    const dialog = page.getByRole('dialog')
    await expect(dialog).toContainText('E2E Resource World')
    const idsAfterOpening = (await (await request.get('/api/worlds', { headers })).json()).worlds.map((world: { id: string }) => world.id)
    expect(idsAfterOpening).toEqual(idsBefore)
    const clonedResponse = page.waitForResponse(response => response.url().endsWith('/api/worlds/clone-from-template') && response.request().method() === 'POST')
    await dialog.getByRole('button', { name: '创建副本并编辑资料册', exact: true }).click()
    const cloned = await (await clonedResponse).json()
    expect(cloned.ok).toBe(true)
    clonedId = cloned.world_id
    await expect(page).toHaveURL(new RegExp(`#/lorebook\\?world=${clonedId}`))
    await expect(page.locator('.lore-context-row--world select')).toHaveValue(clonedId)
    await expect(page.locator('.lore-row')).toContainText('Gate')
    await expect(page.locator('.error-banner')).toHaveCount(0)
    const entries = (await (await request.get(`/api/lorebooks/${encodeURIComponent(`world:${clonedId}`)}/entries`, { headers })).json()).entries
    expect(entries.some((entry: { content: string }) => entry.content === 'Module gate prose')).toBe(true)
    const original = (await (await request.get('/api/worlds/resource_world/definition', { headers })).json()).world
    expect(original).toMatchObject({ source: 'plugin', editable: false, world_name: 'E2E Resource World' })
    expect((await (await request.get('/api/worlds', { headers })).json()).worlds.map((world: { id: string }) => world.id)).not.toContain('resource_world')
    expect(await page.evaluate(() => localStorage.getItem('currentGame'))).toBe(gameKey)
    const game = await (await request.get(`/api/games/${encodeURIComponent(gameKey)}`, { headers })).json()
    expect(game.world_id).toBe('default_fantasy')
  } finally {
    if (clonedId) expect((await request.delete(`/api/worlds/${encodeURIComponent(clonedId)}`, { headers })).ok()).toBe(true)
    expect((await request.post('/api/plugins/e2e-module/stop', { headers })).ok()).toBe(true)
  }
})
