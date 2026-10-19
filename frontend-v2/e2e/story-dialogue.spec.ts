import { expect, test } from './fixtures'
import type { Page, Route } from '@playwright/test'
import { accessToken } from './support'

const GAME = 'web|e2e-room|web_bot'
const GAME_PATH = encodeURIComponent(GAME)
const SPEAKER_A = 's_0123456789abcdef0123'
const SPEAKER_B = 'g_abcdef0123456789abcd'

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'wait' })
})

const savedStory = {
  version: 1 as const,
  segments: [
    { id: 'narration-1', kind: 'narration' as const, text: 'The lantern brightens.' },
    { id: 'dialogue-a', kind: 'dialogue' as const, text: 'Stay close.', speaker_id: SPEAKER_A, speaker_name: 'Mara', portrait: null },
    { id: 'dialogue-b', kind: 'dialogue' as const, text: 'The path is safe.', speaker_id: SPEAKER_B, speaker_name: 'Guide', portrait: null },
  ],
}

const streamStory = {
  version: 1 as const,
  segments: [{ id: 'stream-1', kind: 'dialogue' as const, text: 'Streaming snapshot.', speaker_id: SPEAKER_A, speaker_name: 'Mara', portrait: null }],
}

type StoryRouteState = { createPayload?: Record<string, unknown>; modePayload?: Record<string, unknown>; portraitPut?: Record<string, unknown>; sse: 'story' | 'reset'; story?: typeof savedStory }

async function jsonRoute(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function assertStoryContrast(page: Page): Promise<void> {
  const ratios = await page.locator('.story-sequence').first().evaluate(root => {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 1
    const context = canvas.getContext('2d')!
    function luminance(color: string): number {
      context.clearRect(0, 0, 1, 1)
      context.fillStyle = color; context.fillRect(0, 0, 1, 1)
      const rgb = Array.from(context.getImageData(0, 0, 1, 1).data).slice(0, 3).map(value => {
        const channel = value / 255
        return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4
      })
      return rgb[0]! * .2126 + rgb[1]! * .7152 + rgb[2]! * .0722
    }
    return Array.from(root.querySelectorAll('.story-narrator-card, .story-dialogue-bubble')).map(surface => {
      const text = surface.querySelector('p, span') || surface
      const foreground = luminance(getComputedStyle(text).color)
      const background = luminance(getComputedStyle(surface).backgroundColor)
      return (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05)
    })
  })
  expect(ratios.length).toBeGreaterThan(0)
  for (const ratio of ratios) expect(ratio).toBeGreaterThanOrEqual(4.5)
}

async function installStoryRoutes(page: Page, state: StoryRouteState): Promise<void> {
  const init = { headers: { Authorization: `Bearer ${accessToken()}` } }
  const [detailResponse, logResponse] = await Promise.all([
    page.request.get(`/api/games/${GAME_PATH}`, init),
    page.request.get(`/api/games/${GAME_PATH}/log`, init),
  ])
  expect(detailResponse.ok()).toBeTruthy()
  expect(logResponse.ok()).toBeTruthy()
  const detail = await detailResponse.json() as Record<string, unknown>
  const baseLog = await logResponse.json() as Record<string, unknown>
  await page.route('**/api/games/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = decodeURIComponent(url.pathname)

    if (path.endsWith('/games/create') && request.method() === 'POST') {
      state.createPayload = JSON.parse(request.postData() || '{}') as Record<string, unknown>
      await jsonRoute(route, { ok: true, game_key: GAME, world_name: 'E2E Story' })
      return
    }
    if (path.endsWith(`/games/${GAME}/settings/story-mode`) && request.method() === 'POST') {
      state.modePayload = JSON.parse(request.postData() || '{}') as Record<string, unknown>
      await jsonRoute(route, { ok: true, story_mode: state.modePayload.mode })
      return
    }
    if (path.endsWith(`/games/${GAME}/story-speakers`) && request.method() === 'GET') {
      await jsonRoute(route, { speakers: [
        { id: SPEAKER_A, name: 'Mara', portrait: null },
        { id: SPEAKER_B, name: 'Guide', portrait: null },
      ], total: 2 })
      return
    }
    if (path.includes(`/games/${GAME}/story-speakers/`) && path.endsWith('/portrait') && request.method() === 'PUT') {
      state.portraitPut = JSON.parse(request.postData() || '{}') as Record<string, unknown>
      await jsonRoute(route, { ok: true })
      return
    }
    if (path.endsWith(`/games/${GAME}/sse-ticket`) && request.method() === 'POST') {
      await jsonRoute(route, { ticket: 'e2e-story-ticket' })
      return
    }
    if (path.endsWith(`/games/${GAME}/sse`)) {
      const payload = state.sse === 'story'
        ? { type: 'story_update', story: streamStory }
        : { type: 'narration_reset' }
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: `id: e2e-story\ndata: ${JSON.stringify(payload)}\n\n` })
      return
    }
    if (path === `/api/games/${GAME}` && request.method() === 'GET') {
      await jsonRoute(route, { ...detail, story_mode: state.modePayload?.mode || 'dialogue', state: state.sse === 'story' ? 'active_judgment' : 'active_action' })
      return
    }
    if (path.endsWith(`/games/${GAME}/log`) && request.method() === 'GET') {
      const log = Array.isArray(baseLog.log) ? baseLog.log : []
      await jsonRoute(route, { ...baseLog, log: [...log, { round: 98, story: state.story || savedStory }] })
      return
    }
    await route.continue()
  })
}

test('speech buttons remain aligned beside short and wrapped dialogue', async ({ page }, info) => {
  const state: StoryRouteState = { sse: 'reset', story: { version: 1, segments: [
    { id: 'short', kind: 'dialogue', text: '跟我来。', speaker_id: SPEAKER_A, speaker_name: '守灯人', portrait: null },
    { id: 'long', kind: 'dialogue', text: '码头那边的灯刚刚熄灭了，我们得沿着海边的小路去看看。'.repeat(5), speaker_id: SPEAKER_A, speaker_name: '守灯人', portrait: null },
    { id: 'multiline', kind: 'dialogue', text: '先留在这里。\n我去前面探路，等灯亮起来再跟上。', speaker_id: SPEAKER_B, speaker_name: '向导', portrait: null },
  ] } }
  await installStoryRoutes(page, state)
  await page.goto(`/#/play?game=${GAME_PATH}`)
  const bubbles = page.locator('.story-dialogue-bubble')
  await expect(bubbles).toHaveCount(3)
  await expect(bubbles.first().locator('.story-speech-button')).toBeVisible()
  const geometry = await bubbles.evaluateAll(elements => elements.map(element => {
    const bubble = element.getBoundingClientRect()
    const text = element.querySelector(':scope > span')!
    const textBox = text.getBoundingClientRect()
    const range = document.createRange()
    range.selectNodeContents(text)
    const firstLine = range.getClientRects()[0]!
    const button = element.querySelector('button')!.getBoundingClientRect()
    return { gap: button.left - textBox.right, centerDelta: Math.abs(button.top + button.height / 2 - firstLine.top - firstLine.height / 2), contained: button.right <= bubble.right && button.bottom <= bubble.bottom }
  }))
  for (const item of geometry) {
    expect(item, JSON.stringify(geometry)).toMatchObject({ contained: true })
    expect(item.gap, JSON.stringify(geometry)).toBeGreaterThanOrEqual(6)
    expect(item.centerDelta, JSON.stringify(geometry)).toBeLessThanOrEqual(4)
  }
  await page.getByTestId('story-sequence').screenshot({ path: info.outputPath(`speech-alignment-${info.project.name}.png`) })
})

test('GM can confirm a guest-to-registered identity repair without merging unrelated names', async ({ page }, info) => {
  const guest = 'g_0123456789abcdef0123'
  const state: StoryRouteState = { sse: 'reset', story: { version: 1, segments: [
    { id: 'guest', kind: 'dialogue', text: '旧台词。', speaker_id: guest, speaker_name: '报童', portrait: null },
    { id: 'known', kind: 'dialogue', text: '新台词。', speaker_id: SPEAKER_A, speaker_name: '报童', portrait: null },
  ] } }
  await installStoryRoutes(page, state)
  let merged = false
  await page.route(/\/story-speakers(?:\?.*)?$/, route => jsonRoute(route, { speakers: [
    ...(!merged ? [{ id: guest, name: '报童', first_round: 3 }] : []),
    { id: SPEAKER_A, name: '报童', first_round: 5 },
    { id: SPEAKER_B, name: '向导', first_round: 1 },
  ] }))
  await page.route(/\/story-speakers\/merge(?:\?.*)?$/, async route => {
    expect(route.request().postDataJSON()).toEqual({ source_id: guest, target_id: SPEAKER_A })
    merged = true
    state.story!.segments[0]!.speaker_id = SPEAKER_A
    await jsonRoute(route, { ok: true })
  })
  await page.goto(`/#/play?game=${GAME_PATH}`)
  await page.getByTestId('play-gm-toggle').click()
  await page.getByRole('tab', { name: /设置|Settings/ }).click()
  const cast = page.getByTestId('story-portraits')
  await expect(cast.locator('.story-portrait-row')).toHaveCount(3)
  await cast.locator('.story-merge-controls summary').click()
  await cast.getByTestId('story-merge-target').selectOption(SPEAKER_A)
  await cast.locator('.story-merge-controls button').click()
  expect(merged).toBe(false)
  await page.getByRole('dialog').getByRole('button', { name: '确认合并', exact: true }).click()
  await expect(cast.locator('.story-portrait-row')).toHaveCount(2)
  const settings = page.getByRole('tab', { name: /设置|Settings/ })
  if (!await settings.isVisible()) await page.getByTestId('play-gm-toggle').click()
  await settings.click()
  await expect(cast.locator('.story-speaker-name strong').filter({ hasText: /^向导$/ })).toBeVisible()
  await cast.screenshot({ path: info.outputPath(`cast-repaired-${info.project.name}.png`) })
})

test('creation selector sends story_mode and the saved story renders as narrator and speaker bubbles', async ({ page }, info) => {
  const state: StoryRouteState = { sse: 'reset' }
  await installStoryRoutes(page, state)
  await page.goto('/#/create')
  await page.locator('.create-actions .primary').click()
  const storyMode = page.getByTestId('create-story-mode')
  await expect(storyMode).toBeVisible()
  await storyMode.getByRole('button').filter({ hasText: /角色对话|Character dialogue/ }).click()
  await page.screenshot({ path: info.outputPath(`story-create-${info.project.name}.png`), fullPage: true })
  for (let index = 0; index < 2; index += 1) await page.locator('.create-actions .primary').click()
  await expect(page.locator('.create-confirm-stage')).toBeVisible()
  const createRequest = page.waitForRequest(request => request.url().endsWith('/api/games/create') && request.method() === 'POST')
  await page.getByRole('button', { name: /创建并进入|Create and enter/ }).click()
  await createRequest
  expect(state.createPayload?.story_mode).toBe('dialogue')

  await page.goto(`/#/play?game=${GAME_PATH}`)
  await expect(page.getByTestId('story-sequence')).toBeVisible()
  await expect(page.getByText('The lantern brightens.')).toBeVisible()
  await expect(page.getByText('Stay close.')).toBeVisible()
  await expect(page.getByText('The path is safe.')).toBeVisible()
  await assertStoryContrast(page)
  await page.screenshot({ path: info.outputPath(`story-saved-${info.project.name}.png`), fullPage: true })
  const lightTheme = page.getByRole('button', { name: '切换到浅色主题', exact: true })
  if (await lightTheme.isVisible()) {
    await lightTheme.click()
    await expect(page.getByRole('button', { name: '切换到深色主题', exact: true })).toBeVisible()
    await assertStoryContrast(page)
    await page.screenshot({ path: info.outputPath(`story-saved-light-${info.project.name}.png`), fullPage: true })
  }
})

test('GM can change story mode and manage active cast portraits', async ({ page }, info) => {
  const state: StoryRouteState = { sse: 'reset' }
  await installStoryRoutes(page, state)
  await page.goto(`/#/play?game=${GAME_PATH}`)
  await expect(page.getByTestId('story-sequence')).toBeVisible()
  await page.getByTestId('play-gm-toggle').click()
  await page.getByRole('tab', { name: /设置|Settings/ }).click()
  const mode = page.getByTestId('story-mode-select')
  await expect(mode).toBeVisible()
  await mode.selectOption('prose')
  await expect.poll(() => state.modePayload?.mode).toBe('prose')
  await expect(page.getByText(/叙事头像|Story portraits/)).toBeVisible()
  await page.getByTestId('story-portraits').getByRole('button', { name: /更换头像|Change portrait/ }).first().click()
  await page.locator('.story-portrait-editor > button.primary').click()
  await expect.poll(() => state.portraitPut?.portrait).toBe(null)
  await page.screenshot({ path: info.outputPath(`story-settings-${info.project.name}.png`), fullPage: true })
})

test('story_update streams into the live card and narration_reset clears it', async ({ page }, info) => {
  const state: StoryRouteState = { sse: 'story' }
  await page.addInitScript(() => {
    const NativeSource = window.EventSource
    const target = window as Window & { storyTestSources?: EventSource[] }
    target.storyTestSources = []
    window.EventSource = class extends NativeSource {
      constructor(url: string | URL, configuration?: EventSourceInit) {
        super(url, configuration)
        target.storyTestSources?.push(this)
      }
    }
  })
  await installStoryRoutes(page, state)
  await page.goto(`/#/play?game=${GAME_PATH}`)
  await expect(page.getByText('Streaming snapshot.')).toBeVisible()
  await page.screenshot({ path: info.outputPath(`story-stream-${info.project.name}.png`), fullPage: true })
  await page.evaluate(() => {
    const target = window as Window & { storyTestSources?: EventSource[] }
    for (const source of target.storyTestSources || []) source.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({ type: 'narration_reset' }) }))
  })
  await expect(page.getByTestId('timeline')).toBeVisible()
  await expect(page.locator('.thinking-message .story-sequence')).toHaveCount(0)
  await page.screenshot({ path: info.outputPath(`story-reset-${info.project.name}.png`), fullPage: true })
})
