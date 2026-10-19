import { expect, test } from './fixtures'

const reply = '雾港的钟声响起，调查员沿着石阶走向灯塔。🌙 你可以先了解人物，再决定冒险的开场。'.repeat(16)

test('DF Agent reveals a whole SSE reply progressively while drafts and window controls remain usable', async ({ page }, info) => {
  await page.route('**/api/assistant/agent/run', route => route.fulfill({
    contentType: 'text/event-stream',
    body: [
      `event: draft\ndata: ${JSON.stringify({
        draft_id: '1'.repeat(32),
        review: {
          ok: true, kind: 'world', blockers: [], plan_digest: `sha256:${'a'.repeat(64)}`,
          draft: { source_id: 'progressive-text', filename: 'agent.md', language: 'zh-CN', items: [
            { id: 'setup', name: '雾港草稿', text: '公开的海港与旧灯塔。', target: 'world', references: [] },
          ] },
        },
      })}\n\n`,
      `event: message\ndata: ${JSON.stringify({ delta: reply })}\n\n`,
      'event: done\ndata: complete\n\n',
    ].join(''),
  }))
  await page.goto('/#/overview')
  await page.getByTestId('assistant-shell-fab').click()
  await page.evaluate(() => {
    const state = window as Window & { agentRevealLengths?: number[] }
    state.agentRevealLengths = []
    new MutationObserver(() => {
      const text = document.querySelector('.assistant-message-assistant:last-child .safe-markdown')?.textContent || ''
      if (text.length && state.agentRevealLengths?.at(-1) !== text.length) state.agentRevealLengths?.push(text.length)
    }).observe(document.querySelector('.assistant-transcript')!, { childList: true, subtree: true, characterData: true })
  })
  await page.locator('.assistant-composer textarea').fill('介绍一下这个冒险的开场')
  await page.locator('.assistant-composer textarea').press('Enter')
  const text = page.locator('.assistant-message-assistant .safe-markdown').last()
  await expect.poll(() => text.textContent()).not.toBe('')
  const partial = (await text.textContent()) || ''
  expect(partial.length).toBeGreaterThan(0)
  expect(partial.length).toBeLessThan(reply.length)
  expect(partial).not.toContain('\uFFFD')
  await expect(page.locator('[data-agent-item-name="0"]')).toHaveValue('雾港草稿')
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible()
  await page.getByTestId('assistant-toggle-expanded').click()
  await expect(text).toHaveText(reply, { timeout: 8_000 })
  await expect(page.getByRole('button', { name: '停止', exact: true })).toHaveCount(0)
  const lengths = await page.evaluate(() => (window as Window & { agentRevealLengths?: number[] }).agentRevealLengths || [])
  expect(lengths.filter(length => length < reply.length).length).toBeGreaterThan(2)
  expect(lengths.every((length, index) => index === 0 || length >= lengths[index - 1]!)).toBe(true)
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem('diceframe_assistant_messages') || '[]'))
  expect(stored.at(-1)?.content).toBe(reply)
  await page.screenshot({ path: info.outputPath('agent-progressive-complete.png'), animations: 'disabled', scale: 'css' })
})

test('stopping keeps received text and clearing cancels queued text without restoring old bubbles', async ({ page }) => {
  await page.route('**/api/assistant/agent/run', route => route.fulfill({
    contentType: 'text/event-stream',
    body: `event: message\ndata: ${JSON.stringify({ delta: reply })}\n\nevent: done\ndata: complete\n\n`,
  }))
  await page.goto('/#/overview')
  await page.getByTestId('assistant-shell-fab').click()
  const composer = page.locator('.assistant-composer textarea')
  await composer.fill('给我讲讲雾港')
  await composer.press('Enter')
  await expect(page.locator('.assistant-message-assistant').last().locator('.safe-markdown')).toContainText('雾港')
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '停止', exact: true }).click()
  await expect(page.locator('.assistant-message-assistant .safe-markdown')).toHaveText(reply)
  await expect(page.getByRole('button', { name: '停止', exact: true })).toHaveCount(0)

  await composer.fill('再写一段开场')
  await composer.press('Enter')
  await expect(page.locator('.assistant-message-assistant').last().locator('.safe-markdown')).toContainText('雾港')
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible()
  await page.locator('.assistant-panel-head button[title="清空"]').click()
  await expect(page.locator('.assistant-message')).toHaveCount(0)
  await expect(page.locator('.assistant-empty')).toBeVisible()
  await page.waitForTimeout(200)
  await expect(page.locator('.assistant-message')).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('diceframe_assistant_messages'))).toBeNull()
})
