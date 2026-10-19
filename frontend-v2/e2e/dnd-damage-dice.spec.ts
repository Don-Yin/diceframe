import { expect, test } from './fixtures'
import { accessToken } from './support'

test('dnd5e character editor preserves damage dice, fixed fallback, and equipment identity', async ({ page, request }, info) => {
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  const suffix = `${Date.now()}-${info.project.name}`
  const createdResponse = await request.post('/api/games/create', {
    headers,
    data: {
      world_id: 'freeform_sandbox',
      game_name: `E2E damage dice ${suffix}`,
      rule_id: 'dnd5e',
      solo: true,
      room_password: '',
      language: 'zh-CN',
      players: [{
        character_name: `骰式角色 ${suffix}`,
        attributes: { str: 10, dex: 10, con: 10, int: 10, wis: 10, cha: 10 },
        equipment: [{
          name: '长剑', type: 'weapon', damage: 7, damage_dice: '1d8',
          damage_type: 'slashing', item_key: 'longsword', slot: 'main_hand', quality: 'common',
        }],
      }],
    },
  })
  const created = await createdResponse.json()
  expect(createdResponse.ok(), JSON.stringify(created)).toBe(true)
  const gameKey = String(created.game_key || '')
  expect(gameKey).toBeTruthy()

  try {
    const charactersResponse = await request.get(`/api/games/${encodeURIComponent(gameKey)}/characters`, { headers })
    const characters = await charactersResponse.json()
    expect(charactersResponse.ok(), JSON.stringify(characters)).toBe(true)
    const player = characters.players.find((entry: { character_name?: string }) => entry.character_name === `骰式角色 ${suffix}`)
    expect(player).toBeTruthy()
    const userId = String(player.user_id)
    const route = `/#/characters?game=${encodeURIComponent(gameKey)}&edit_user=${encodeURIComponent(userId)}`

    await page.goto(route)
    const dialog = page.getByRole('dialog').last()
    await expect(dialog).toBeVisible()
    const diceInput = dialog.locator('.item-dice')
    await expect(diceInput).toHaveValue('1d8')
    await expect(diceInput).toHaveAttribute('aria-label', /伤害骰|Damage dice/)
    await diceInput.fill('2d6+1')
    await dialog.getByRole('button', { name: '保存', exact: true }).click()
    await expect(dialog).toHaveCount(0)

    const afterValidResponse = await request.get(`/api/games/${encodeURIComponent(gameKey)}/characters`, { headers })
    const afterValid = await afterValidResponse.json()
    const validEquipment = afterValid.players.find((entry: { user_id: string }) => entry.user_id === userId).character_sheet.equipment[0]
    expect(validEquipment).toEqual(expect.objectContaining({ damage_dice: '2d6+1', damage: 7, item_key: 'longsword', damage_type: 'slashing' }))

    await page.locator('.current-character-card').filter({ hasText: `骰式角色 ${suffix}` }).getByRole('button', { name: '编辑', exact: true }).click()
    const invalidDialog = page.getByRole('dialog').last()
    await expect(invalidDialog.locator('.item-dice')).toHaveValue('2d6+1')
    await invalidDialog.locator('.item-dice').fill('1d8+1d6')
    await invalidDialog.getByRole('button', { name: '保存', exact: true }).click()
    await expect(invalidDialog).toBeVisible()
    await expect(invalidDialog.getByRole('alert')).toContainText('伤害骰公式无效')
    await expect(page.locator('.n-message').filter({ hasText: '伤害骰公式无效' })).toBeInViewport()
    const afterInvalidResponse = await request.get(`/api/games/${encodeURIComponent(gameKey)}/characters`, { headers })
    const afterInvalid = await afterInvalidResponse.json()
    const invalidEquipment = afterInvalid.players.find((entry: { user_id: string }) => entry.user_id === userId).character_sheet.equipment[0]
    expect(invalidEquipment).toEqual(expect.objectContaining({ damage_dice: '2d6+1', damage: 7, item_key: 'longsword' }))

    const modalOverflow = await invalidDialog.evaluate(element => element.scrollWidth - element.clientWidth)
    expect(modalOverflow).toBeLessThanOrEqual(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
    await invalidDialog.screenshot({ path: info.outputPath(`dnd-damage-dice-invalid-${info.project.name}.png`), scale: 'css' })
  } finally {
    const deleted = await request.delete(`/api/games/${encodeURIComponent(gameKey)}`, { headers })
    expect(deleted.ok(), `cleanup failed: ${await deleted.text()}`).toBe(true)
  }
})
