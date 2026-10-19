import { expect, test } from './fixtures'
import { accessToken, seatTakeoverPath } from './support'

for (const width of [1280, 1024]) test(`settings and logs menus remain reachable at ${width}x480`, async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop')
  await page.addInitScript(() => localStorage.setItem('currentGame', 'web|e2e-room|web_bot'))
  await page.route(/\/api\/games\/[^/]+\/log(?:\?.*)?$/, async route => {
    const response = await route.fetch()
    const data = await response.json()
    await route.fulfill({ response, json: { ...data, total: 20, log: Array.from({ length: 20 }, (_, index) => ({ round: index + 1, actions: [], gm_response: '长日志布局验证。'.repeat(30) })) } })
  })
  await page.setViewportSize({ width, height: 480 })
  for (const route of ['settings?section=models', 'logs']) {
    await page.goto(`/#/${route}`)
    const menu = page.locator(route.startsWith('settings') ? '.settings-nav' : '.log-index')
    await expect(menu).toBeVisible()
    if (route === 'logs') await expect(page.locator('.log-reader article')).toHaveCount(20)
    await menu.evaluate(element => element.scrollIntoView({ block: 'start' }))
    const geometry = await menu.evaluate(element => {
      const box = element.getBoundingClientRect()
      const content = document.querySelector('.settings-content, .logs-document')!.getBoundingClientRect()
      return { bottom: box.bottom, viewport: innerHeight, gap: content.left - box.right }
    })
    expect(geometry.bottom).toBeLessThanOrEqual(geometry.viewport - 8)
    expect(geometry.gap).toBeGreaterThanOrEqual(14)
    if (route.startsWith('settings')) {
      await page.locator('.settings-nav [data-section="security"]').click()
      await expect(page.locator('#settings-security')).toBeVisible()
    } else {
      await page.locator('.log-index-tabs button').last().click()
      await expect(page.locator('.console-log')).toBeVisible()
      await page.locator('.log-index-tabs button').first().click()
      await page.locator('.log-index .log-export').scrollIntoViewIfNeeded()
      await expect(page.locator('.log-index .log-export')).toBeInViewport()
    }
    await page.screenshot({ path: info.outputPath(`menu-${route.split('?')[0]}.png`) })
  }
})

test('module mode asks for a package before checking compatibility', async ({ page }, info) => {
  await page.goto('/#/create')
  await page.locator('.create-play-mode button').last().click()
  await expect(page.locator('[role="status"]', { hasText: '请先选择一个冒险包' })).toBeVisible()
  await expect(page.locator('.adventure-issue-actions')).toHaveCount(0)
  await expect(page.locator('.create-actions .primary')).toBeDisabled()
  await page.screenshot({ path: info.outputPath(`choose-package-${info.project.name}.png`) })
})

for (const solo of [false, true]) test(`an invited ${solo ? 'solo' : 'multiplayer'} player retains readable messages and an on-screen composer`, async ({ browser, request }, info) => {
  const key = 'web|e2e-room|web_bot'
  const headers = { Authorization: `Bearer ${accessToken()}` }
  const games = await (await request.get('/api/games', { headers })).json()
  const game = games.games.find((item: { game_key: string }) => item.game_key === key)
  const chars = await (await request.get(`/api/games/${encodeURIComponent(key)}/characters`, { headers })).json()
  const player = chars.players.find((item: { user_id: string }) => item.user_id !== game.gm_uid)
  const context = await browser.newContext()
  const page = await context.newPage()
  // Exercise both public layouts using the real seat authorization/projection.
  // Only the table mode varies; no owner credentials enter the player's browser.
  await page.route(new RegExp(`/api/games/${encodeURIComponent(key)}(?:\\?.*)?$`), async route => {
    const response = await route.fetch()
    await route.fulfill({ response, json: { ...await response.json(), solo_mode: solo } })
  })
  await page.setViewportSize(info.project.name === 'mobile' ? { width: 390, height: 844 } : { width: 2515, height: 1256 })
  await page.goto(await seatTakeoverPath(request, key, player.user_id))
  await expect(page).toHaveURL(/#\/play\?/, { timeout: 20_000 })
  await expect(page.getByTestId('timeline')).toBeVisible()
  const geometry = await page.locator('.play-page').evaluate(element => {
    const box = element.getBoundingClientRect()
    const composer = element.querySelector('.composer')!.getBoundingClientRect()
    const main = element.querySelector('.play-main')!.getBoundingClientRect()
    const hud = element.querySelector('.play-hud')!.getBoundingClientRect()
    return { top: box.top, bottom: box.bottom, viewport: innerHeight, composerBottom: composer.bottom, mainWidth: main.width, mainTop: main.top, hudBottom: hud.bottom, scrollWidth: document.documentElement.scrollWidth, width: innerWidth }
  })
  await page.screenshot({ path: info.outputPath(`invite-${solo ? 'solo' : 'multiplayer'}-${info.project.name}.png`) })
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.width + 1)
  expect(geometry.top).toBeGreaterThanOrEqual(0)
  expect(geometry.composerBottom).toBeLessThanOrEqual(geometry.viewport + 1)
  expect(geometry.mainTop).toBeLessThanOrEqual(geometry.hudBottom + 12)
  expect(geometry.mainWidth).toBeGreaterThan(geometry.width * .55)
  await expect(page.locator('.message.gm .message-copy')).toBeVisible()
  const messages = page.locator('.message.player .message-copy')
  await expect(messages).toHaveCount(2)
  for (const message of await messages.all()) {
    await expect(message).toBeVisible()
    expect((await message.boundingBox())!.width).toBeGreaterThan(140)
    await expect(message.locator('p')).not.toBeEmpty()
  }
  await expect(page.getByPlaceholder('用自然语言描述行动')).toBeVisible()
  const tools = page.getByTestId('play-tools-toggle')
  const exposed = await tools.evaluate(element => {
    const box = element.getBoundingClientRect()
    return element.contains(document.elementFromPoint(box.right - 6, box.top + box.height / 2))
  })
  expect(exposed).toBe(true)
  await expect(page.getByTestId('play-gm-toggle')).toHaveCount(0)
  await expect(page.getByTestId('play-gm-drawer')).toHaveCount(0)
  await tools.click()
  await expect(page.getByTestId('play-collaboration-toggle')).toHaveCount(0)
  await page.keyboard.press('Escape')
  if (info.project.name === 'mobile') {
    const styles = await page.locator('[data-testid="play-character-toggle"], .kp-question-tool-trigger').evaluateAll(elements => elements.map(element => {
      const style = getComputedStyle(element)
      const isLeft = element.matches('.mobile-drawer-trigger-left')
      return {
        color: style.borderTopColor, width: style.borderTopWidth, background: style.backgroundColor,
        shadow: style.boxShadow, height: element.getBoundingClientRect().height,
        innerBorder: isLeft ? style.borderRight : style.borderLeft,
        outerBorder: isLeft ? style.borderLeft : style.borderRight,
        innerTopRadius: isLeft ? style.borderTopRightRadius : style.borderTopLeftRadius,
        innerBottomRadius: isLeft ? style.borderBottomRightRadius : style.borderBottomLeftRadius,
        outerTopRadius: isLeft ? style.borderTopLeftRadius : style.borderTopRightRadius,
        outerBottomRadius: isLeft ? style.borderBottomLeftRadius : style.borderBottomRightRadius,
      }
    }))
    expect(styles).toHaveLength(2)
    expect(styles[0]).toEqual(styles[1])
  }
  await page.screenshot({ path: info.outputPath(`invite-${solo ? 'solo' : 'multiplayer'}-${info.project.name}.png`) })
  await context.close()
})
