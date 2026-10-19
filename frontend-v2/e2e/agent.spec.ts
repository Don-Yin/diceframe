import { expect, test } from './fixtures'
import { prepareAuthenticatedPage } from './support'

async function openWorkspace(page: import('@playwright/test').Page) {
  const toggle = page.getByTestId('assistant-workspace-toggle')
  if (await toggle.getAttribute('aria-expanded') === 'false') await toggle.click()
}

test('DF Agent keeps an existing-book confirmation visible at the end of a long conversation', async ({ page, request }, testInfo) => {
  await prepareAuthenticatedPage(page, request)
  await page.addInitScript(() => {
    const history = Array.from({ length: 16 }, (_, index) => ({
      role: index % 2 ? 'assistant' : 'user',
      content: `${index + 1}. ${'此前讨论世界设定和资料册条目的内容。'.repeat(20)}`,
    }))
    localStorage.setItem('diceframe_assistant_messages', JSON.stringify(history))
    localStorage.removeItem('diceframe_assistant_session_id')
  })
  await page.route('**/api/assistant/agent/run', route => route.fulfill({
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
    body: [
      'event: status\ndata: {"message":"正在规划下一步…"}\n\n',
      `event: approval\ndata: ${JSON.stringify({
        approval_id: 'a'.repeat(32), plan_digest: `sha256:${'b'.repeat(64)}`,
        tool: 'write_lorebook_entries', label: 'Add lorebook entry',
        arguments: { book_id: 'arkham', entries: [{ name: '旧书店', content: '雨夜里的旧书店。' }] },
        preview: { target_name: '克苏鲁恐怖·阿卡姆疑云' }, expires_at: 4102444800,
      })}\n\n`,
      'event: done\ndata: complete\n\n',
    ].join(''),
  }))
  await page.goto('/#/overview')
  await page.getByTestId('assistant-shell-fab').click()
  await page.locator('.assistant-composer textarea').fill('给克苏鲁恐怖·阿卡姆疑云资料册随便加一条')
  await page.locator('.assistant-composer textarea').press('Enter')
  const approval = page.locator('[data-agent-approval]')
  await expect(approval).toContainText('克苏鲁恐怖·阿卡姆疑云')
  await openWorkspace(page)
  await expect(approval.getByRole('button', { name: '确认执行' })).toBeInViewport()
  await expect(page.locator('.assistant-message-assistant').last()).toContainText('等待确认')
  await expect(page.locator('.assistant-composer-hint')).toContainText('等待确认')
  await page.screenshot({ path: testInfo.outputPath('agent-existing-book-approval.png') })
})

test('DF Agent carries a reviewed draft through approval and across routes', async ({ page, request }, testInfo) => {
  let runCount = 0
  let reviewedDraft: Record<string, unknown> | null = null
  let confirmed = false
  await page.route('**/api/assistant/agent/session/**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ ok: true, session_id: '00112233445566778899aabbccddeeff', pending: null, drafts: {}, receipts: [], status: 'idle' }),
  }))
  await page.route('**/api/assistant/agent/run', route => {
    runCount += 1
    const body = runCount === 1
      ? [
        'event: session\ndata: {"session_id":"0123456789abcdef0123456789abcdef"}\n\n',
        'event: draft\ndata: {"draft_id":"abcdef0123456789abcdef0123456789","review":{"ok":true,"kind":"world","plan_digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","blockers":[],"draft":{"source_id":"source-1","filename":"agent.md","language":"zh-CN","items":[{"id":"item-1","name":"Old name","text":"Old text","target":"world","references":[]}]}}}\n\n',
        'event: approval\ndata: {"approval_id":"fedcba9876543210fedcba9876543210","plan_digest":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","tool":"save_content","label":"Save content","arguments":{"draft_id":"abcdef0123456789abcdef0123456789"},"expires_at":4102444800}\n\n',
        'event: done\ndata: complete\n\n',
      ].join('')
      : 'event: approval\ndata: {"approval_id":"1234567890abcdef1234567890abcdef","plan_digest":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","tool":"save_content","label":"Save content","arguments":{"draft_id":"abcdef0123456789abcdef0123456789"},"preview":{"target_name":"海港世界"},"expires_at":4102444800}\n\nevent: done\ndata: complete\n\n'
    return route.fulfill({ status: 200, headers: { 'Content-Type': 'text/event-stream' }, body })
  })
  await page.route('**/api/assistant/agent/review', async route => {
    reviewedDraft = route.request().postDataJSON().draft
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, draft_id: 'abcdef0123456789abcdef0123456789', review: { ok: true, kind: 'world', plan_digest: 'sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd', blockers: [], draft: reviewedDraft } }) })
  })
  await page.route('**/api/assistant/agent/confirm', async route => {
    if (route.request().postDataJSON().approved === false) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, cancelled: true }) })
    }
    confirmed = true
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, result: { created: true, id: 'world-1' }, navigation: { route: '/play', query: { game: 'game-1' } } }) })
  })

  await prepareAuthenticatedPage(page, request)
  await page.goto('/#/overview')
  await page.getByTestId('assistant-shell-fab').click()
  await page.getByRole('button', { name: '创作内容' }).click()
  const card = page.locator('[data-agent-draft="abcdef0123456789abcdef0123456789"]')
  await openWorkspace(page)
  await expect(card).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('agent-panel.png') })

  const composer = page.locator('.assistant-composer textarea')
  const itemName = card.locator('[data-agent-item-name="0"]')
  await itemName.fill('New name')
  await expect(card.locator('[data-agent-save]')).toBeDisabled()
  await composer.fill('展开期间保留的未发送任务草稿')
  const runCountBeforeExpand = runCount
  await page.getByTestId('assistant-toggle-expanded').click()
  await expect(page.locator('.assistant-shell-expanded')).toHaveCount(1)
  await expect(page.locator('.assistant-transcript')).toBeVisible()
  await expect(page.locator('.assistant-tasks')).toBeVisible()
  await expect(composer).toHaveValue('展开期间保留的未发送任务草稿')
  await expect(itemName).toHaveValue('New name')
  expect(runCount).toBe(runCountBeforeExpand)

  const expandedBox = await page.locator('.assistant-shell-expanded').boundingBox()
  const viewport = page.viewportSize()
  expect(expandedBox).not.toBeNull()
  expect(viewport).not.toBeNull()
  expect(expandedBox!.x).toBeGreaterThanOrEqual(0)
  expect(expandedBox!.y).toBeGreaterThanOrEqual(0)
  expect(expandedBox!.x + expandedBox!.width).toBeLessThanOrEqual(viewport!.width)
  expect(expandedBox!.y + expandedBox!.height).toBeLessThanOrEqual(viewport!.height)
  if (viewport!.width > 800) {
    expect(expandedBox!.width).toBeGreaterThan(440)
    const transcriptBox = await page.locator('.assistant-transcript').boundingBox()
    const tasksBox = await page.locator('.assistant-tasks').boundingBox()
    expect(tasksBox!.x).toBeGreaterThan(transcriptBox!.x)
    const chatFraction = transcriptBox!.width / (transcriptBox!.width + tasksBox!.width)
    expect(chatFraction).toBeGreaterThanOrEqual(0.68)
    expect(chatFraction).toBeLessThanOrEqual(0.72)
    expect(tasksBox!.width).toBeGreaterThanOrEqual(280)
  }
  await page.screenshot({ path: testInfo.outputPath('agent-expanded-window.png') })

  await page.getByTestId('assistant-toggle-expanded').click()
  await expect(page.locator('.assistant-shell-expanded')).toHaveCount(0)
  await expect(composer).toHaveValue('展开期间保留的未发送任务草稿')
  await expect(itemName).toHaveValue('New name')
  expect(runCount).toBe(runCountBeforeExpand)

  await expect(card.locator('[data-agent-save]')).toBeDisabled()
  await card.locator('[data-agent-review]').click()
  await expect.poll(() => reviewedDraft).toMatchObject({ source_id: 'source-1', items: [{ name: 'New name' }] })
  expect(confirmed).toBe(false)
  await card.locator('[data-agent-save]').click()
  await expect(page.locator('[data-agent-approval]')).toBeVisible()
  await expect(page.locator('[data-agent-approval]')).toContainText('海港世界')
  await page.getByTestId('assistant-toggle-expanded').click()
  await expect(page.locator('.assistant-shell-expanded')).toHaveCount(1)
  await expect(page.locator('[data-agent-approval] button').first()).toBeInViewport()
  await page.screenshot({ path: testInfo.outputPath('agent-approval.png') })
  await page.locator('[data-agent-approval] button').first().click()
  await expect.poll(() => confirmed).toBe(true)
  await expect(page.getByRole('button', { name: '打开游戏' })).toBeVisible()
  await page.getByRole('button', { name: '打开游戏' }).click()
  await expect(page).toHaveURL(/#\/play\?game=game-1/)
  await expect(page.getByTestId('assistant-shell-fab')).toBeVisible()

  await page.locator('.assistant-panel-head button').last().click()
  await page.goto('/#/settings?section=general&focus=agent')
  await expect(page.locator('#settings-agent')).toBeVisible()
  const entrySwitch = page.locator('#settings-agent .advanced-row').filter({ has: page.locator('strong', { hasText: 'DF Agent' }) }).getByRole('switch')
  await entrySwitch.click()
  await expect(page.getByTestId('assistant-shell-fab')).toHaveCount(0)
  await entrySwitch.click()
  await expect(page.getByTestId('assistant-shell-fab')).toBeVisible()
})
