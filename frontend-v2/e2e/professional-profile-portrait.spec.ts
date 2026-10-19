import { expect, test } from './fixtures'

test('character profile portraits use one selectable frame on desktop and mobile', async ({ page }, info) => {
  await page.route(/\/api\/character-cards(?:\?|$)/, route => route.fulfill({ json: { cards: [{
    card_id: 'layout:profile', character_name: '头像验收角色', rule_id: 'dnd2024_srd',
    ruleset_runtime: { id: 'core:dnd2024', capabilities: { character_lifecycle: 'rules_aware' } },
    ruleset_character: { build: { level: 1 } },
  }] } }))
  await page.goto('/#/characters?game=web%7Ce2e-room%7Cweb_bot')
  await page.getByRole('button', { name: '高级角色中心', exact: true }).click()
  const center = page.locator('.professional-character-center')
  await expect(center.getByRole('button', { name: '基础信息', exact: true })).toBeVisible()
  await center.getByRole('button', { name: '人物资料', exact: true }).click()
  const option = center.locator('.portrait-picker > .portrait-options .portrait-option').first()
  await option.click()
  await expect(option).toHaveAttribute('aria-pressed', 'true')
  const frames = await option.evaluate(button => ({
    button: getComputedStyle(button).borderTopWidth,
    portrait: getComputedStyle(button.querySelector('.portrait-image')!).borderTopWidth,
    portraitShadow: getComputedStyle(button.querySelector('.portrait-image')!).boxShadow,
  }))
  expect(frames.button).toBe('1px')
  expect(frames.portrait).toBe('0px')
  expect(frames.portraitShadow).toBe('none')
  await center.locator('.portrait-picker').screenshot({ path: info.outputPath('profile-portrait-single-frame.png'), scale: 'css' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
})
