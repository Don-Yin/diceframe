import { expect, test } from './fixtures'
import { accessToken } from './support'

test('new world operations expose and persist the same fields as editing', async ({ page, request }, info) => {
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  let worldId = ''
  try {
    await page.goto('/#/lorebook?world=default_fantasy')
    await page.getByTestId('world-actions').click()
    await page.getByRole('button', { name: '新建世界', exact: true }).click()
    const creator = page.locator('.lore-world-creator')
    await expect(creator.getByRole('button', { name: '创建', exact: true })).toBeDisabled()
    await creator.locator('.world-metadata-editor input').fill(`完整新世界 ${info.project.name}`)
    await creator.locator('.world-metadata-editor textarea').fill('仅供浏览的简要介绍')
    await creator.getByTestId('world-setting').fill('完整背景：群岛上的灯塔会移动。')
    await creator.getByTestId('starter-scene').fill('默认开场：你收到一封来自无人岛的信。')
    await creator.screenshot({ path: info.outputPath('new-world-full-form.png'), scale: 'css' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
    const creating = page.waitForResponse(response => response.url().endsWith('/api/worlds') && response.request().method() === 'POST')
    await creator.getByRole('button', { name: '创建', exact: true }).click()
    const created = await (await creating).json()
    expect(created.ok).toBe(true)
    worldId = created.world_id
    await expect(creator).toHaveCount(0)
    await expect(page.locator('.lore-context-select').first()).toHaveValue(worldId)
    await expect(page).toHaveURL(url => new URLSearchParams(url.hash.split('?')[1] || '').get('world') === worldId)
    await page.reload()
    await page.getByTestId('world-actions').click()
    await page.getByRole('button', { name: '编辑世界', exact: true }).click()
    await expect(page.locator('.world-metadata-editor textarea')).toHaveValue('仅供浏览的简要介绍')
    await expect(page.getByTestId('world-setting')).toHaveValue('完整背景：群岛上的灯塔会移动。')
    await expect(page.getByTestId('starter-scene')).toHaveValue('默认开场：你收到一封来自无人岛的信。')
  } finally {
    if (worldId) expect((await request.delete(`/api/worlds/${encodeURIComponent(worldId)}`, { headers })).ok()).toBe(true)
  }
})

test('lorebook world operations edit the full definition and preserve the active game', async ({ page, request }, info) => {
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  const created = await (await request.post('/api/worlds', {
    headers, data: { name: `资料页验收 ${info.project.name}`, description: '简要介绍', language: 'zh-CN' },
  })).json()
  expect(created.ok).toBe(true)
  const worldId = created.world_id
  const originalSetting = '完整背景：这是一个雾气笼罩的群岛世界。'
  const originalOpening = '默认开场：你在一座废弃灯塔的门口醒来。'
  const seeded = await request.put(`/api/worlds/${encodeURIComponent(worldId)}`, {
    headers, data: { name: created.name, description: '简要介绍', language: 'zh-CN', world_setting: originalSetting, starter_scene: originalOpening },
  })
  expect(seeded.ok()).toBe(true)
  const gameKey = 'web|e2e-room|web_bot'
  const gameBefore = (await (await request.get(`/api/games/${encodeURIComponent(gameKey)}`, { headers })).json())
  expect(gameBefore.world_id).toBe('default_fantasy')
  await page.addInitScript(key => localStorage.setItem('currentGame', key), gameKey)
  try {
    await page.goto(`/#/lorebook?world=${encodeURIComponent(worldId)}`)
    await expect(page.locator('.lore-context-select').first()).toHaveValue(worldId)
    await page.getByTestId('world-actions').click()
    await page.getByRole('button', { name: '编辑世界', exact: true }).click()
    // This is the exact entry in the user's screenshot, with no gallery navigation.
    await expect(page.getByTestId('world-setting')).toHaveValue(originalSetting)
    await expect(page.getByTestId('starter-scene')).toHaveValue(originalOpening)
    await expect(page).toHaveURL(/#\/lorebook\?world=/)
    const nextSetting = `${originalSetting}\n群岛中央的海水会在午夜倒流。`
    const nextOpening = `${originalOpening}\n灯塔内传出三声敲击。`
    await page.getByTestId('world-setting').fill(nextSetting)
    await page.getByTestId('starter-scene').fill(nextOpening)
    // A rejected save should retain the draft and allow a second attempt.
    const worldEndpoint = `**/api/worlds/${encodeURIComponent(worldId)}`
    await page.route(worldEndpoint, async route => {
      if (route.request().method() === 'PUT') return route.fulfill({ status: 409, json: { ok: false, error: '验收：暂时保存失败' } })
      return route.continue()
    })
    await page.getByRole('button', { name: '保存', exact: true }).click()
    await expect(page.locator('.world-definition-error')).toContainText('验收：暂时保存失败')
    await expect(page.getByTestId('world-setting')).toHaveValue(nextSetting)
    await expect(page.getByTestId('starter-scene')).toHaveValue(nextOpening)
    await expect(page.getByRole('button', { name: '保存', exact: true })).toBeEnabled()
    await page.unroute(worldEndpoint)
    await page.getByRole('button', { name: '保存', exact: true }).click()
    await expect(page.getByTestId('world-setting')).toHaveCount(0)
    const saved = (await (await request.get(`/api/worlds/${encodeURIComponent(worldId)}/definition`, { headers })).json()).world
    expect(saved).toMatchObject({ world_setting: nextSetting, starter_scene: nextOpening, description: '简要介绍' })
    expect(await page.evaluate(() => localStorage.getItem('currentGame'))).toBe(gameKey)
    const gameAfter = (await (await request.get(`/api/games/${encodeURIComponent(gameKey)}`, { headers })).json())
    expect(gameAfter.world_id).toBe(gameBefore.world_id)
    expect(gameAfter.world_name).toBe(gameBefore.world_name)
    await page.reload()
    await page.getByTestId('world-actions').click()
    await page.getByRole('button', { name: '编辑世界', exact: true }).click()
    await expect(page.getByTestId('world-setting')).toHaveValue(nextSetting)
    await expect(page.getByTestId('starter-scene')).toHaveValue(nextOpening)
    await page.locator('.lore-world-editor').screenshot({ path: info.outputPath('lorebook-world-editor.png'), scale: 'css' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  } finally {
    expect((await request.delete(`/api/worlds/${encodeURIComponent(worldId)}`, { headers })).ok()).toBe(true)
  }
})

test('builtin background is readable from lorebook operations and cloning opens an editable copy', async ({ page, request }, info) => {
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  const sourceId = 'default_fantasy'
  const source = (await (await request.get(`/api/worlds/${sourceId}/definition?language=zh-CN`, { headers })).json()).world
  expect(source.source).toBe('builtin')
  const gameKey = 'web|e2e-room|web_bot'
  const gameBefore = (await (await request.get(`/api/games/${encodeURIComponent(gameKey)}`, { headers })).json())
  expect(gameBefore.world_id).toBe('default_fantasy')
  await page.addInitScript(key => localStorage.setItem('currentGame', key), gameKey)
  let clonedId = ''
  try {
    await page.goto(`/#/lorebook?world=${sourceId}`)
    await page.getByTestId('world-actions').click()
    await page.getByRole('button', { name: '编辑世界', exact: true }).click()
    await expect(page.getByTestId('world-setting')).toHaveValue(source.world_setting)
    await expect(page.getByTestId('world-setting')).toHaveAttribute('readonly', '')
    const clonedResponse = page.waitForResponse(response => response.url().endsWith('/api/worlds/clone-from-template') && response.request().method() === 'POST')
    await page.getByRole('button', { name: '克隆为我的世界并编辑', exact: true }).click()
    const cloned = await (await clonedResponse).json()
    expect(cloned.ok).toBe(true)
    clonedId = cloned.world_id
    await expect(page.getByTestId('world-setting')).not.toHaveAttribute('readonly', '')
    // The copied canonical text can differ from a readonly locale overlay.
    const own = (await (await request.get(`/api/worlds/${encodeURIComponent(clonedId)}/definition`, { headers })).json()).world
    await expect(page.getByTestId('world-setting')).toHaveValue(own.world_setting)
    await expect(page.locator('.lore-context-select').first()).toHaveValue(clonedId)
    await page.getByTestId('world-setting').fill(`克隆世界的独立背景 ${info.project.name}`)
    await page.getByRole('button', { name: '保存', exact: true }).click()
    await expect(page.getByTestId('world-setting')).toHaveCount(0)
    const untouched = (await (await request.get(`/api/worlds/${sourceId}/definition?language=zh-CN`, { headers })).json()).world
    expect(untouched).toEqual(source)
    expect(await page.evaluate(() => localStorage.getItem('currentGame'))).toBe(gameKey)
    const gameAfter = (await (await request.get(`/api/games/${encodeURIComponent(gameKey)}`, { headers })).json())
    expect(gameAfter.world_id).toBe(gameBefore.world_id)
    expect(gameAfter.world_name).toBe(gameBefore.world_name)
  } finally {
    if (clonedId) expect((await request.delete(`/api/worlds/${encodeURIComponent(clonedId)}`, { headers })).ok()).toBe(true)
  }
})
