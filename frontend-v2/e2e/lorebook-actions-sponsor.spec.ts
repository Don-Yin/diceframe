import { expect, test } from './fixtures'

test('content recovery sits beside AI generation and remains usable', async ({ page }, info) => {
  await page.goto('/#/lorebook?world=freeform_sandbox')
  const tools = page.locator('.lore-tools')
  const generate = tools.getByRole('button', { name: 'AI 生成', exact: true })
  const recovery = tools.getByTestId('content-recovery-open')
  await expect(generate).toBeVisible()
  await expect(recovery).toBeVisible()
  const generateBox = await generate.boundingBox()
  const recoveryBox = await recovery.boundingBox()
  expect(Math.abs(generateBox!.y - recoveryBox!.y)).toBeLessThanOrEqual(1)
  expect(recoveryBox!.x).toBeGreaterThanOrEqual(generateBox!.x + generateBox!.width)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  await tools.screenshot({ path: info.outputPath('lorebook-content-actions.png'), scale: 'css' })
  await recovery.click()
  await expect(page.getByRole('dialog', { name: '内容撤销 / 回收站', exact: true })).toBeVisible()
})

test('WeChat sponsor image loads from the built frontend assets', async ({ page }, info) => {
  await page.goto('/#/settings?section=about')
  await page.locator('.sponsor-cta').click()
  const modal = page.locator('.sponsor-modal')
  const image = modal.getByAltText('微信赞助二维码')
  await expect(modal).toBeVisible()
  const source = await image.getAttribute('src')
  expect(source).toBeTruthy()
  const response = await page.request.get(source!)
  expect(response.ok()).toBe(true)
  expect(response.headers()['content-type']).toContain('image/png')
  await expect.poll(() => image.evaluate(element => {
    const img = element as HTMLImageElement
    return img.complete && img.naturalWidth > 0 && img.naturalHeight > 0
  })).toBe(true)
  expect(await image.evaluate(element => {
    const img = element as HTMLImageElement
    return Math.abs(img.clientWidth / img.clientHeight - img.naturalWidth / img.naturalHeight)
  })).toBeLessThan(0.02)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  await modal.screenshot({ path: info.outputPath('wechat-sponsor.png'), scale: 'css' })
})
