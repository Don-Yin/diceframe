import { expect, test } from './fixtures'

test('upgrade validation notice clears after commitment and fits a narrow screen', async ({ page }) => {
  let pending = true
  await page.route('**/api/system/update/health', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ ok: true, update_pending: pending }),
  }))
  await page.setViewportSize({ width: 320, height: 720 })
  await page.goto('/#/overview')
  const notice = page.getByRole('status').filter({ hasText: '更新正在验证' })
  await expect(notice).toBeVisible()
  const box = await notice.boundingBox()
  expect(box).not.toBeNull()
  expect(box!.x).toBeGreaterThanOrEqual(0)
  expect(box!.x + box!.width).toBeLessThanOrEqual(320)
  pending = false
  await expect(notice).toHaveCount(0)
})
