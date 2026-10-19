import { expect, test } from './fixtures'
import { accessToken } from './support'

test('save actions upload a cover, refresh cards and restore the content default', async ({ page, request }, info) => {
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  const targetKey = 'web|e2e-room|web_bot'
  const otherKey = 'web|e2e-dnd2024|web_bot'
  const endpoint = `/api/games/${encodeURIComponent(targetKey)}`
  const target = await (await request.get(endpoint, { headers })).json()
  const otherBefore = await (await request.get(`/api/games/${encodeURIComponent(otherKey)}`, { headers })).json()
  await page.addInitScript(key => localStorage.setItem('currentGame', key), otherKey)
  await page.goto('/#/overview')
  const card = page.locator(`.game-card[data-game-key="${targetKey}"]`)
  await expect(card).toHaveCount(1)
  await expect(card.getByRole('heading', { name: target.world_name, exact: true })).toBeVisible()
  const originalSource = await card.locator('.game-card-art').getAttribute('style')
  await card.locator('.overview-game-tools > summary').click()
  await card.getByTestId('save-change-cover').click()
  const dialog = page.getByRole('dialog', { name: '冒险头图', exact: true })
  await expect(dialog).toContainText(target.world_name)
  await dialog.locator('input[type="file"]').setInputFiles('public/ui/rules/rule-freeform-coc.webp')
  await expect(dialog).toContainText('冒险专属')
  await dialog.screenshot({ path: info.outputPath('save-cover-dialog.png'), scale: 'css' })
  try {
    // A failed write keeps the same draft available for retry.
    const failedEndpoint = `**/api/games/${encodeURIComponent(targetKey)}/scene-image`
    await page.route(failedEndpoint, route => route.request().method() === 'POST'
      ? route.fulfill({ status: 409, json: { ok: false, error: '验收：头图暂未保存' } })
      : route.continue())
    await dialog.getByTestId('save-cover-save').click()
    await expect(dialog.getByRole('alert')).toContainText('验收：头图暂未保存')
    await expect(dialog).toContainText('冒险专属')
    await page.unroute(failedEndpoint)
    // Saving a cover succeeds independently of a later archive-index read.
    await page.route('**/api/games', route => route.fulfill({ status: 503, json: { error: '验收：存档列表暂不可读' } }))
    await dialog.getByTestId('save-cover-save').click()
    await expect(dialog).toHaveCount(0)
    const uploaded = await (await request.get(endpoint, { headers })).json()
    expect(uploaded.scene_image.kind).toBe('upload')
    await expect(card.locator('.game-card-art')).not.toHaveAttribute('style', originalSource!)
    await expect.poll(() => card.locator('.game-card-art').getAttribute('style')).toContain('blob:')
    await page.unroute('**/api/games')
    await page.reload()
    await expect.poll(() => card.locator('.game-card-art').getAttribute('style')).toContain('blob:')
    expect((await (await request.get(endpoint, { headers })).json()).scene_image).toEqual(uploaded.scene_image)
    expect(await page.evaluate(() => localStorage.getItem('currentGame'))).toBe(otherKey)
    const otherAfter = await (await request.get(`/api/games/${encodeURIComponent(otherKey)}`, { headers })).json()
    expect(otherAfter.scene_image).toEqual(otherBefore.scene_image)
    expect(uploaded.world_id).toBe(target.world_id)
    expect(uploaded.round_number).toBe(target.round_number)
    await card.locator('.overview-game-tools > summary').click()
    await card.getByTestId('save-change-cover').click()
    await dialog.getByRole('button', { name: '使用内容默认', exact: true }).click()
    await dialog.getByTestId('save-cover-save').click()
    await expect(dialog).toHaveCount(0)
    await expect.poll(() => card.locator('.game-card-art').getAttribute('style')).not.toContain('blob:')
    expect((await (await request.get(endpoint, { headers })).json()).scene_image.kind).toBe('builtin')
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  } finally {
    const restore = target.scene_image?.kind ? { scene_image: target.scene_image } : { use_default: true }
    expect((await request.post(`${endpoint}/scene-image`, { headers, data: restore })).ok()).toBe(true)
  }
})
