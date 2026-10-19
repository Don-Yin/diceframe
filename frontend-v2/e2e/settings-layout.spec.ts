import { expect, test } from './fixtures'

test('settings keep search above navigation and render one aligned active pane', async ({ page }, info) => {
  for (const section of ['general', 'models', 'about']) {
    const config = section === 'general'
      ? page.waitForResponse(response => response.url().endsWith('/api/config') && response.request().method() === 'GET')
      : Promise.resolve()
    await page.goto(`/#/settings?section=${section}`)
    await config
    await expect(page.locator('.settings-nav .nav-item.active')).toHaveAttribute('data-section', section)
    await expect(page.locator('.settings-content .n-spin-content')).not.toHaveClass(/n-spin-content--spinning/)
    await expect(page.locator('.settings-nav .settings-search')).toBeVisible()
    await expect(page.getByTestId('settings-search')).toHaveAttribute('placeholder', '搜索')
    expect(await page.locator('.settings-nav-group-label').allTextContents()).toEqual(['模型与 AI', '连接与集成', '安全与隐私', '通用'])
    for (const id of ['general', 'appearance', 'about']) {
      await expect(page.locator(`.settings-nav [data-section="${id}"]`)).toHaveAttribute('data-group', 'general')
    }
    for (const id of ['voice', 'agent', 'system']) await expect(page.locator(`.settings-nav [data-section="${id}"]`)).toHaveCount(0)
    const panes = page.locator('.settings-pane:visible')
    await expect(panes).toHaveCount(1)
    const geometry = await panes.first().evaluate(element => {
      const box = element.getBoundingClientRect()
      const layout = document.querySelector('.settings-content')!.getBoundingClientRect()
      return { top: box.top, layoutTop: layout.top, width: box.width, scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }
    })
    expect(geometry.scrollWidth - geometry.clientWidth, section).toBeLessThanOrEqual(1)
    if (info.project.name === 'desktop') expect(Math.abs(geometry.top - geometry.layoutTop), section).toBeLessThanOrEqual(2)
    if (section === 'about') await expect(page.locator('.about-links')).toBeVisible()
    if (section === 'general') {
      await page.screenshot({ path: info.outputPath('settings-general-top.png'), scale: 'css' })
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
      for (const id of ['settings-language', 'settings-tts', 'settings-agent', 'settings-agent-budget', 'settings-runtime-logs', 'settings-test-timeout']) {
        await expect(panes.locator(`#${id}`)).toBeVisible()
      }
      const cards = await panes.locator('.advanced-section').evaluateAll(elements => elements.map(element => ({ width: element.clientWidth, scrollWidth: element.scrollWidth })))
      expect(cards).toHaveLength(5)
      for (const card of cards) expect(card.scrollWidth - card.width).toBeLessThanOrEqual(1)
      await page.locator('#settings-test-timeout').scrollIntoViewIfNeeded()
      await expect(page.locator('#settings-test-timeout')).toBeInViewport()
      const saved = page.waitForResponse(response => response.url().endsWith('/api/config') && response.request().method() === 'POST')
      await page.locator('#settings-test-timeout').getByRole('button', { name: '保存', exact: true }).click()
      const response = await saved
      expect(response.ok()).toBe(true)
      expect(Object.keys(response.request().postDataJSON())).toEqual(['test_timeout_seconds'])
      await page.locator('#settings-language').scrollIntoViewIfNeeded()
    }
    if (section === 'models') {
      const advanced = page.locator('details.generation-settings')
      await expect(advanced).not.toHaveAttribute('open')
      await advanced.locator('summary').click()
      await expect(page.locator('#settings-generation-options')).toBeVisible()
      await expect(page.locator('#settings-generation')).toBeVisible()
      await expect(advanced.locator('footer button')).toHaveCount(1)
      const boxes = await page.locator('.model-role-card-main, .generation-settings').evaluateAll(elements => elements.map(element => {
        const box = element.getBoundingClientRect()
        return { left: box.left, right: box.right, width: box.width, scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }
      }))
      expect(Math.abs(boxes[0]!.left - boxes[1]!.left)).toBeLessThanOrEqual(1)
      expect(Math.abs(boxes[0]!.right - boxes[1]!.right)).toBeLessThanOrEqual(1)
      expect(boxes[1]!.scrollWidth - boxes[1]!.clientWidth).toBeLessThanOrEqual(1)
      await advanced.screenshot({ path: info.outputPath('advanced-generation.png'), style: '.app-header, .content-workspace-rail, .assistant-launcher { visibility: hidden !important; }' })
      await expect(page.locator('.model-capability-grid > .model-capability-column')).toHaveCount(2)
      await expect(page.locator('#settings-check-model')).toBeVisible()
      const widths = await page.locator('.model-role-card:visible > header > div').evaluateAll(elements => elements.map(element => element.getBoundingClientRect().width))
      expect(Math.min(...widths)).toBeGreaterThan(100)
    }
    await page.screenshot({ path: info.outputPath(`settings-${section}.png`), fullPage: true })
  }
})

test('previous voice, Agent and maintenance links locate their section inside General', async ({ page }) => {
  for (const [section, target] of [['voice', 'settings-tts'], ['agent', 'settings-agent'], ['system', 'settings-runtime-logs']]) {
    await page.goto(`/#/settings?section=${section}`)
    await expect(page.locator('.settings-nav .nav-item.active')).toHaveAttribute('data-section', 'general')
    await expect(page.locator(`#${target}`)).toHaveClass(/settings-search-highlight/)
    await expect(page.locator(`#${target}`)).toBeInViewport()
    await expect(page.locator('.settings-pane:visible')).toHaveCount(1)
  }
})
