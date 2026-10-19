import { expect, test } from './fixtures'

test('phone task workspace folds without losing edits or covering the conversation', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile', 'This contract covers the compact phone workspace.')
  await page.setViewportSize({ width: 390, height: 740 })
  let runs = 0
  await page.route('**/api/assistant/agent/run', route => {
    runs += 1
    const draft = {
      draft_id: 'abcdef0123456789abcdef0123456789',
      review: { ok: true, kind: 'world', plan_digest: `sha256:${'a'.repeat(64)}`, blockers: [], draft: {
        source_id: 'source-1', filename: 'agent.md', language: 'zh-CN',
        items: Array.from({ length: 20 }, (_, index) => ({ id: `item-${index}`, name: `地点 ${index}`, text: '待编辑的地点背景。'.repeat(12), target: 'world', references: [] })),
      } },
    }
    return route.fulfill({ status: 200, contentType: 'text/event-stream', body: [
      `event: draft\ndata: ${JSON.stringify(draft)}\n\n`,
      `event: approval\ndata: ${JSON.stringify({ approval_id: 'b'.repeat(32), plan_digest: `sha256:${'c'.repeat(64)}`, tool: 'save_content', label: 'Save', arguments: { draft_id: draft.draft_id }, expires_at: 4102444800 })}\n\n`,
      'event: done\ndata: complete\n\n',
    ].join('') })
  })
  await page.goto('/#/overview')
  await page.getByTestId('assistant-shell-fab').click()
  const composer = page.locator('.assistant-composer textarea')
  await composer.fill('整理这些地点资料')
  await composer.press('Enter')
  const toggle = page.getByTestId('assistant-workspace-toggle')
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect(toggle).toContainText('等待确认')
  await expect(page.locator('[data-agent-draft]')).toBeHidden()
  await expect(page.locator('.assistant-transcript')).toBeVisible()
  const panel = (await page.locator('.assistant-panel').boundingBox())!
  expect((await page.locator('.assistant-transcript').boundingBox())!.height).toBeGreaterThan(panel.height * .45)

  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  await expect(page.locator('[data-agent-approval] button').first()).toBeInViewport()
  expect((await page.locator('.assistant-transcript').boundingBox())!.height).toBeGreaterThan(panel.height * .3)
  const name = page.locator('[data-agent-item-name="0"]')
  await name.fill('保留的修改')
  await composer.fill('尚未发送的后续说明')
  await toggle.click()
  await expect(name).toBeHidden()
  await toggle.click()
  await expect(name).toHaveValue('保留的修改')
  await expect(composer).toHaveValue('尚未发送的后续说明')
  expect(runs).toBe(1)
  await toggle.click()
  await page.screenshot({ path: info.outputPath('agent-workspace-folded.png'), scale: 'css' })
})

test('general settings recover a misplaced Agent launcher without clearing chat', async ({ page }, info) => {
  await page.addInitScript(() => {
    localStorage.setItem('diceframe_assistant_launcher_position', '{"x":0,"y":0}')
    localStorage.setItem('diceframe_assistant_messages', JSON.stringify([{ role: 'user', content: '保留我的对话' }]))
  })
  await page.goto('/#/settings?section=general&focus=agent')
  const recover = page.getByTestId('assistant-reset-position')
  await recover.scrollIntoViewIfNeeded()
  await recover.click()
  const launcher = page.getByTestId('assistant-shell-fab')
  await expect.poll(async () => (await launcher.boundingBox())!.x).toBeGreaterThan(page.viewportSize()!.width - 90)
  expect(await page.evaluate(() => localStorage.getItem('diceframe_assistant_launcher_position'))).toBeNull()
  await launcher.click()
  await expect(page.locator('.assistant-message-user')).toContainText('保留我的对话')
  await page.screenshot({ path: info.outputPath('agent-position-recovered.png'), scale: 'css' })
})

for (const route of ['/#/library', '/#/settings?section=appearance']) test(`secondary navigation remains below the header when scrolling ${route}`, async ({ page }, info) => {
  await page.goto(route)
  const rail = page.locator('.content-workspace-rail')
  await expect(rail).toBeVisible()
  await page.mouse.wheel(0, 650)
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(20)
  const headerBox = (await page.locator('.app-header').boundingBox())!
  const railBox = (await rail.boundingBox())!
  expect(railBox.y).toBeGreaterThanOrEqual(headerBox.y + headerBox.height - 1)
  expect(railBox.y).toBeLessThanOrEqual(headerBox.y + headerBox.height + 1)
  await expect(rail.locator('a').first()).toBeInViewport()
  if (route.includes('settings') && page.viewportSize()!.width <= 900) {
    const sectionMenu = page.locator('.settings-nav')
    const sectionBox = (await sectionMenu.boundingBox())!
    expect(sectionBox.y).toBeGreaterThanOrEqual(railBox.y + railBox.height)
    await expect(sectionMenu.getByRole('button', { name: '外观主题' }).first()).toBeInViewport()
  }
  await page.screenshot({ path: info.outputPath('secondary-navigation-fixed.png'), scale: 'css' })
})

for (const route of ['/#/library', '/#/settings?section=general']) test(`secondary navigation takes the top position as the primary header scrolls away ${route}`, async ({ page }, info) => {
  await page.setViewportSize({ width: page.viewportSize()!.width, height: 480 })
  await page.goto(route)
  if (route.includes('library')) await expect(page.getByTestId('content-library')).toHaveAttribute('aria-busy', 'false')
  const header = page.locator('.app-header')
  const rail = page.locator('.content-workspace-rail')
  await expect(rail).toBeVisible()
  const headerHeight = (await header.boundingBox())!.height

  const partialScroll = Math.round(480 - headerHeight / 2)
  for (const scrollY of [0, partialScroll, 680, partialScroll, 0]) {
    await page.evaluate(y => window.scrollTo(0, y), scrollY)
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(scrollY)
    const headerBox = (await header.boundingBox())!
    const expectedTop = Math.max(0, headerBox.y + headerBox.height)
    if (scrollY === 680) {
      expect(expectedTop).toBe(0)
    }
    await expect.poll(async () => (await rail.boundingBox())!.y).toBeCloseTo(expectedTop, 0)
    await expect(rail.locator('a').first()).toBeInViewport()
    if (scrollY === 680) {
      if (route.includes('settings')) {
        await expect.poll(async () => {
          const railBox = (await rail.boundingBox())!
          const settingsBox = (await page.locator('.settings-nav').boundingBox())!
          const gap = settingsBox.y - railBox.y - railBox.height
          return gap >= 8 && gap <= 12
        }).toBe(true)
      }
      await page.screenshot({ path: info.outputPath('secondary-navigation-primary-hidden.png'), scale: 'css' })
    }
  }

  const originalWidth = page.viewportSize()!.width
  for (const width of [originalWidth <= 800 ? 1024 : 390, originalWidth]) {
    await page.setViewportSize({ width, height: 480 })
    await expect.poll(async () => {
      const headerBox = (await header.boundingBox())!
      const railBox = (await rail.boundingBox())!
      return Math.abs(railBox.y - headerBox.y - headerBox.height)
    }).toBeLessThanOrEqual(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  }
})
