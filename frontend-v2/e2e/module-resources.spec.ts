import { expect, test } from './fixtures'
import { accessToken } from './support'

test('installed module resources fork edited native content into real user libraries', async ({ page, request }, info) => {
  test.setTimeout(90_000)
  const suffix = info.project.name
  await page.goto('/#/modules/e2e-module')
  await expect(page.getByTestId('resource-open').first()).toBeVisible()
  const list = page.locator('.resource-list')
  for (const [resourceName, copyName, target] of [
    ['E2E Resource World', `Module World ${suffix}`, 'world'],
    ['E2E Resource Hero', `Module Hero ${suffix}`, 'character_template'],
    ['E2E 模组冒险', `Module Quest ${suffix}`, 'adventure'],
  ]) {
    await page.getByTestId('resource-search').fill(resourceName!)
    await expect(list.locator('li')).toHaveCount(1)
    await list.getByTestId('resource-open').click()
    await page.getByTestId('resource-fork').click()
    await page.getByTestId('fork-name').fill(copyName!)
    if (target === 'character_template') await page.getByTestId('fork-text').fill('Module copy edited background.')
    await page.getByTestId('fork-reviewed').check()
    await expect(page.getByTestId('fork-save')).toBeDisabled()
    await page.getByTestId('fork-review').click()
    await page.getByTestId('fork-reviewed').check()
    await expect(page.getByTestId('fork-save')).toBeEnabled()
    const response = page.waitForResponse(response => response.url().endsWith('/resources/fork/commit'))
    await page.getByTestId('fork-save').click()
    const result = await (await response).json()
    expect(result.ok, JSON.stringify(result)).toBe(true)
    await expect(page.getByTestId('fork-saved')).toBeVisible()
    const geometry = await page.locator('.module-fork-dialog').evaluate(element => ({ overflow: element.scrollWidth - element.clientWidth, right: element.getBoundingClientRect().right, width: innerWidth }))
    expect(geometry.overflow).toBeLessThanOrEqual(1); expect(geometry.right).toBeLessThanOrEqual(geometry.width)
    await page.screenshot({ path: info.outputPath(`module-fork-${target}.png`), fullPage: true })
    await page.locator('.module-fork-dialog .modal-x').click()
  }
  const headers = { Authorization: `Bearer ${accessToken()}` }
  const worlds = await (await request.get('/api/worlds', { headers })).json()
  expect(worlds.worlds.some((world: { name: string }) => world.name === `Module World ${suffix}`)).toBe(true)
  const cards = await (await request.get('/api/character-cards', { headers })).json()
  expect(cards.cards.find((card: { character_name: string }) => card.character_name === `Module Hero ${suffix}`).background).toBe('Module copy edited background.')
  await page.goto('/#/adventures')
  await expect(page.locator('.adventure-package-card').filter({ has: page.getByRole('heading', { name: `Module Quest ${suffix}`, exact: true }) })).toBeVisible()
})
