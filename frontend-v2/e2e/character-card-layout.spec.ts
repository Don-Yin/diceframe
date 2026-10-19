import { expect, test } from './fixtures'

const game = 'web|e2e-room|web_bot'

test('角色卡库的不同按钮数量仍保持卡片和动作区整齐', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'desktop card geometry contract')

  await page.route(/\/api\/character-cards(?:\?|$)/, route => route.request().method() !== 'GET'
    ? route.continue()
    : route.fulfill({ json: { cards: [
      {
        card_id: 'layout:professional',
        character_name: '职业测试者',
        rule_id: 'dnd2024_srd',
        rule_name: '5E 2024 SRD 高级规则',
        race: '半身人',
        class: '游荡者',
        background: '职业卡需要职业升级和高级角色中心两个额外动作。',
        ruleset_runtime: {
          id: 'core:dnd2024',
          capabilities: { character_lifecycle: 'rules_aware' },
        },
        ruleset_character: { build: { level: 1 } },
      },
      {
        card_id: 'layout:ordinary-a',
        character_name: '普通测试者 A',
        rule_id: 'freeform_fantasy',
        rule_name: '自由幻想',
        race: '人类',
        class: '战士',
        background: '普通卡只显示编辑、导出和删除。',
      },
      {
        card_id: 'layout:ordinary-b',
        character_name: '普通测试者 B',
        rule_id: 'freeform_fantasy',
        rule_name: '自由幻想',
        race: '精灵',
        class: '法师',
        background: '第二张普通卡用于验证同一网格中的高度。',
      },
    ] } }))

  await page.setViewportSize({ width: 1366, height: 900 })
  await page.goto(`/#/characters?game=${encodeURIComponent(game)}`)
  const tabs = page.getByRole('tab')
  await expect(tabs).toHaveCount(2)
  await expect(page.getByRole('tab', { name: '角色卡库', exact: true })).toHaveAttribute('aria-selected', 'true')
  const tabGeometry = await tabs.evaluateAll(elements => elements.map(element => {
    const rect = element.getBoundingClientRect()
    return { width: rect.width, height: rect.height, overflow: element.scrollWidth - element.clientWidth }
  }))
  expect(Math.max(...tabGeometry.map(item => item.width)) - Math.min(...tabGeometry.map(item => item.width))).toBeLessThanOrEqual(1)
  expect(Math.max(...tabGeometry.map(item => item.height)) - Math.min(...tabGeometry.map(item => item.height))).toBeLessThanOrEqual(1)
  expect(tabGeometry[0].height).toBeGreaterThanOrEqual(40)
  for (const tab of tabGeometry) expect(tab.overflow).toBeLessThanOrEqual(1)
  const tabGroup = (await page.locator('.character-collection-tabs').boundingBox())!
  const pageContent = (await page.locator('.characters-page').boundingBox())!
  expect(Math.abs(tabGroup.x + tabGroup.width / 2 - pageContent.x - pageContent.width / 2)).toBeLessThanOrEqual(2)
  await expect(page.locator('.library-character-card').filter({ hasText: '职业测试者' })).toBeVisible()

  const geometry = await page.locator('.library-character-card').evaluateAll(elements => elements.map(element => {
    const card = element.getBoundingClientRect()
    const portrait = element.querySelector<HTMLElement>('.portrait-image')!.getBoundingClientRect()
    const actions = element.querySelector<HTMLElement>('.actions')!.getBoundingClientRect()
    const buttons = Array.from(element.querySelectorAll<HTMLElement>('.actions button')).map(button => {
      const rect = button.getBoundingClientRect()
      return { top: rect.top, width: rect.width, height: rect.height }
    })
    return {
      name: element.querySelector('h2')?.textContent?.trim(),
      card: { left: card.left, top: card.top, width: card.width, height: card.height, bottom: card.bottom },
      portrait: { width: portrait.width, height: portrait.height },
      actions: { top: actions.top, bottom: actions.bottom },
      buttons,
    }
  }))

  expect(geometry).toHaveLength(3)
  expect(Math.max(...geometry.map(item => item.card.width)) - Math.min(...geometry.map(item => item.card.width))).toBeLessThanOrEqual(1)
  expect(Math.max(...geometry.map(item => item.card.height)) - Math.min(...geometry.map(item => item.card.height))).toBeLessThanOrEqual(1)
  expect(Math.max(...geometry.map(item => item.portrait.width)) - Math.min(...geometry.map(item => item.portrait.width))).toBeLessThanOrEqual(1)
  expect(Math.max(...geometry.map(item => item.portrait.height)) - Math.min(...geometry.map(item => item.portrait.height))).toBeLessThanOrEqual(1)

  for (const item of geometry) {
    expect(Math.abs(item.card.bottom - item.actions.bottom - 11)).toBeLessThanOrEqual(2)
    expect(Math.max(...item.buttons.map(button => button.height)) - Math.min(...item.buttons.map(button => button.height))).toBeLessThanOrEqual(1)
    expect(Math.max(...item.buttons.map(button => button.width)) - Math.min(...item.buttons.map(button => button.width))).toBeLessThanOrEqual(1)
  }

  const professional = geometry.find(item => item.name === '职业测试者')!
  const ordinary = geometry.find(item => item.name === '普通测试者 A')!
  const professionalRows = new Map<number, number>()
  for (const button of professional.buttons) professionalRows.set(button.top, (professionalRows.get(button.top) || 0) + 1)
  expect([...professionalRows.values()]).toEqual([2, 2])
  expect(new Set(ordinary.buttons.map(button => button.top)).size).toBe(1)
})
