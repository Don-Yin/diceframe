import { expect, test } from './fixtures'

const cards = [
  { card_id: 'picker:short', character_name: '阿兰', race: '人类', class: '游荡者', portrait: { kind: 'builtin', id: 'dnd5e:1' } },
  { card_id: 'picker:long', character_name: '来自远方的守林人', rule_id: 'freeform_fantasy', rule_name: '经典奇幻自由规则', race: '半身人', class: '战士' },
  { card_id: 'picker:convert', character_name: '调查员', rule_id: 'freeform_coc', rule_name: 'CoC 7e 调查恐怖轻量规则', race: '人类', class: '私家侦探' },
  { card_id: 'picker:wrap', character_name: 'AsterOfTheSilverForest'.repeat(4), rule_id: 'custom:long', rule_name: 'A detailed custom ruleset with a long translated display name', race: 'High elf', class: 'Oath of the Ancients paladin' },
  ...Array.from({ length: 14 }, (_, index) => ({ card_id: `picker:extra-${index}`, character_name: `冒险者 ${index + 1}`, race: '人类', class: '战士' })),
]

for (const locale of ['zh-CN', 'en']) {
  test(`character choices align portraits and text and keep long lists usable (${locale})`, async ({ page }, info) => {
    await page.addInitScript(value => localStorage.setItem('diceframe_locale', value), locale)
    await page.route(/\/api\/character-cards(?:\?|$)/, route => route.fulfill({ json: { cards } }))
    await page.goto('/#/create')
    const next = page.locator('.create-actions .primary')
    await expect(next).toBeEnabled()
    await next.click()
    await next.click()
    await page.locator('.create-character-actions > button').nth(1).click()
    const dialog = page.locator('.modal .dialog').filter({ has: page.locator('.card-choice') })
    const choices = dialog.locator('.card-choice')
    await expect(choices).toHaveCount(cards.length)
    await dialog.screenshot({ path: info.outputPath(`character-card-picker-${locale}.png`), scale: 'css' })
    const geometry = await choices.evaluateAll(elements => elements.map(element => {
      const row = element.getBoundingClientRect()
      const portrait = element.querySelector('.portrait-image')!.getBoundingClientRect()
      const copy = element.querySelector('.card-choice-copy')!
      const text = copy.getBoundingClientRect()
      return {
        display: getComputedStyle(element).display,
        portraitLeft: portrait.left,
        textLeft: text.left,
        inset: portrait.left - row.left,
        gap: text.left - portrait.right,
        height: row.height,
        overflow: copy.scrollWidth - copy.clientWidth,
      }
    }))
    expect(geometry.every(row => row.display === 'grid')).toBe(true)
    expect(Math.max(...geometry.map(row => row.portraitLeft)) - Math.min(...geometry.map(row => row.portraitLeft))).toBeLessThanOrEqual(1)
    expect(Math.max(...geometry.map(row => row.textLeft)) - Math.min(...geometry.map(row => row.textLeft))).toBeLessThanOrEqual(1)
    for (const row of geometry) {
      expect(row.inset).toBeLessThanOrEqual(15)
      expect(row.gap).toBeGreaterThanOrEqual(10)
      expect(row.height).toBeGreaterThanOrEqual(72)
      expect(row.overflow).toBeLessThanOrEqual(1)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
    const headerBefore = await dialog.locator('header').boundingBox()
    await choices.last().scrollIntoViewIfNeeded()
    await expect(choices.last()).toBeInViewport()
    const headerAfter = await dialog.locator('header').boundingBox()
    expect(Math.abs(headerAfter!.y - headerBefore!.y)).toBeLessThanOrEqual(1)
    await expect(dialog.locator('header button')).toBeInViewport()
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
  })
}
