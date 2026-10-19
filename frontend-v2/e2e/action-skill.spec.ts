import { expect, test } from './fixtures'
import { PLAY_READY_TIMEOUT, accessToken } from './support'

test('an explicit skill is optional, submitted without bonuses, and retained with a failed draft', async ({ page, request }, info) => {
  const characterUrl = '/api/games/web%7Ce2e-room%7Cweb_bot/character/e2e-gm'
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  const prepared = await request.put(characterUrl, { headers, data: { skills: [{ name: '侦查', value: 60 }] } })
  expect(prepared.ok(), await prepared.text()).toBe(true)
  let sent: Record<string, unknown> | undefined
  let failSubmission = true
  await page.route(/\/api\/games\/[^/]+\/action(?:\?|$)/, async route => {
    sent = route.request().postDataJSON()
    await route.fulfill(failSubmission
      ? { status: 409, json: { ok: false, error_code: 'ROUND_PROCESSING_FAILED', error: 'Synthetic rolled-back round' } }
      : { status: 200, json: { ok: true, phase: 'waiting' } })
  })
  await page.goto('/#/play?game=web%7Ce2e-room%7Cweb_bot')
  const options = page.locator('.action-check-options')
  await expect(options).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
  async function assertStackedInsideInput() {
    const frame = (await page.getByTestId('composer-input').boundingBox())!
    const action = (await page.locator('.composer-input-actions > .primary').boundingBox())!
    expect(action.x).toBeGreaterThan(frame.x)
    expect(action.x + action.width).toBeLessThanOrEqual(frame.x + frame.width - 6)
    expect(action.height).toBeGreaterThanOrEqual(36)
    expect(action.y + action.height).toBeLessThanOrEqual(frame.y + frame.height - 6)
    expect(frame.x + frame.width - action.x - action.width).toBeLessThanOrEqual(12)
    const skill = (await options.boundingBox())!
    expect(skill.y - frame.y).toBeGreaterThanOrEqual(6)
    expect(skill.y - frame.y).toBeLessThanOrEqual(8)
    expect(action.y).toBeGreaterThanOrEqual(skill.y + skill.height + 4)
    expect(Math.abs(skill.x - action.x)).toBeLessThanOrEqual(1)
    expect(Math.abs(skill.width - action.width)).toBeLessThanOrEqual(1)
    const summary = (await options.locator('summary').boundingBox())!
    expect(summary.height).toBeGreaterThanOrEqual(40)
    expect(summary.height).toBeLessThanOrEqual(48)
    expect((await page.locator('.composer-input-actions').boundingBox())!.width).toBeLessThanOrEqual(80)
  }
  for (const width of info.project.name === 'mobile' ? [320, 390, 740] : [801, 980, 1280]) {
    await page.setViewportSize({ width, height: 900 })
    const input = (await page.locator('.composer textarea').boundingBox())!
    const frame = (await page.getByTestId('composer-input').boundingBox())!
    const control = (await options.boundingBox())!
    expect(control.x, `${width}px skill control belongs to the right of the text`).toBeGreaterThanOrEqual(input.x + input.width + 4)
    expect(control.x + control.width).toBeLessThan(frame.x + frame.width)
    expect(frame.width).toBeGreaterThan(130)
    expect(input.width).toBeGreaterThan(80)
    await assertStackedInsideInput()
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  }
  await page.route(/\/api\/config(?:\?|$)/, async route => {
    const response = await route.fetch()
    const config = await response.json()
    await route.fulfill({ response, json: { ...config, asr_provider: 'openai-compatible', asr_provider_ref: 'layout-asr', ai_providers: [...(config.ai_providers || []), { id: 'layout-asr', name: 'Layout ASR', base_url: 'http://localhost:8000/v1', api_format: 'openai' }] } })
  })
  await page.reload()
  await expect(page.locator('.composer-row .dictation-toggle')).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
  for (const width of info.project.name === 'mobile' ? [320, 390] : [801, 1280]) {
    await page.setViewportSize({ width, height: 900 })
    const input = (await page.locator('.composer textarea').boundingBox())!
    const frame = (await page.getByTestId('composer-input').boundingBox())!
    const control = (await options.boundingBox())!
    expect(control.x).toBeGreaterThanOrEqual(input.x + input.width + 4)
    expect(control.x + control.width).toBeLessThan(frame.x + frame.width)
    expect(input.width).toBeGreaterThan(80)
    await assertStackedInsideInput()
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  }
  await expect(options).not.toHaveAttribute('open')
  const closedComposerHeight = (await page.locator('.composer').boundingBox())!.height
  await options.locator('summary').click()
  await expect(options.locator('.action-check-menu')).toBeVisible()
  expect((await page.locator('.composer').boundingBox())!.height).toBe(closedComposerHeight)
  await page.screenshot({ path: info.outputPath('skill-menu-open.png'), scale: 'css' })
  await page.keyboard.press('Escape')
  await expect(options).not.toHaveAttribute('open')
  await options.locator('summary').click()
  await page.locator('.composer textarea').click()
  await expect(options).not.toHaveAttribute('open')
  await options.locator('summary').click()
  const select = options.locator('select')
  const skill = await select.locator('option').nth(1).getAttribute('value')
  expect(skill).toBeTruthy()
  await select.selectOption(skill!)
  await expect(options).not.toHaveAttribute('open')
  await page.locator('.composer textarea').fill('我明确使用这个技能跨过裂缝')
  await page.locator('.composer-row').screenshot({ path: info.outputPath('stacked-skill-and-action.png'), scale: 'css' })
  await page.locator('.composer-input-actions > .primary').click()
  await expect.poll(() => sent).toEqual({ text: '我明确使用这个技能跨过裂缝', selected_skill: skill })
  await page.reload()
  await expect(options).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
  await expect(select).toHaveValue(skill!)
  await expect(page.locator('.composer textarea')).toHaveValue('我明确使用这个技能跨过裂缝')
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  await page.locator('.composer').screenshot({ path: info.outputPath('explicit-action-skill.png') })
  failSubmission = false
  await page.locator('.composer-input-actions > .primary').click()
  await expect(select).toHaveValue('')
  await expect(options.locator('summary')).toContainText('自动判断')
  await page.locator('.composer textarea').fill('我接着询问守卫')
  await page.locator('.composer-input-actions > .primary').click()
  await expect.poll(() => sent).toEqual({ text: '我接着询问守卫' })
  const restored = await request.put(characterUrl, { headers, data: { skills: [] } })
  expect(restored.ok()).toBe(true)
})
