import { expect, test } from './fixtures'

test('creation narrative choices share the same columns and spacing', async ({ page }, info) => {
  await page.goto('/#/create')
  const next = page.locator('.create-actions .primary')
  await expect(next).toBeEnabled()
  await next.click()
  const fields = page.locator('.create-game-settings-stage .narrative-perspective-field')
  await expect(fields).toHaveCount(3)
  const boxes = await fields.evaluateAll(elements => elements.map(element => {
    const rect = element.getBoundingClientRect()
    const buttons = [...element.querySelectorAll('.narrative-perspective-cards > button')].map(button => {
      const box = button.getBoundingClientRect()
      return { left: box.left, right: box.right, top: box.top, bottom: box.bottom }
    })
    return { left: rect.left, right: rect.right, buttons }
  }))
  expect(Math.max(...boxes.map(box => box.left)) - Math.min(...boxes.map(box => box.left))).toBeLessThanOrEqual(1)
  expect(Math.max(...boxes.map(box => box.right)) - Math.min(...boxes.map(box => box.right))).toBeLessThanOrEqual(1)
  for (const column of [0, 1]) {
    expect(Math.max(...boxes.map(box => box.buttons[column].left)) - Math.min(...boxes.map(box => box.buttons[column].left))).toBeLessThanOrEqual(1)
  }
  await page.screenshot({ path: info.outputPath('creation-choices.png'), fullPage: true })
})
