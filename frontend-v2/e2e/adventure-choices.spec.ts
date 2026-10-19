import { expect, test } from './fixtures'
import { accessToken, seatTakeoverPath } from './support'

test('player proposes a private route and GM confirms one saved branch', async ({ page, browser, request }, info) => {
  const key = `web|e2e_choice_${info.project.name}|web_bot`
  const path = `/api/games/${encodeURIComponent(key)}`
  const playerContext = await browser.newContext({ viewport: { width: 390, height: 844 } })
  try {
    const player = await playerContext.newPage()
    const takeoverPath = await seatTakeoverPath(request, key, 'e2e-player')
    await player.goto(takeoverPath)
    const playerPanel = player.getByTestId('game-adventure-panel')
    await player.getByTestId('adventure-panel-toggle').click()
    await expect(playerPanel).not.toContainText('Secret ritual')
    await playerPanel.getByTestId('adventure-choice-gate-bridge_route').click()
    await expect(playerPanel).toContainText('等待 GM 确认')
    const seatToken = new URLSearchParams(takeoverPath.split('?')[1]).get('seat')!
    const forbidden = await (await player.request.post(`${path}/intents?user=e2e-player`, {
      headers: { 'X-Seat-Token': seatToken },
      data: { type: 'adventure.node.complete', node_id: 'gate', choice_id: 'bridge_route' },
    })).json()
    expect(forbidden.code).toBe('GM_ONLY')
    await page.goto(`/#/play?game=${encodeURIComponent(key)}`)
    const gmPanel = page.getByTestId('game-adventure-panel')
    await page.getByTestId('adventure-panel-toggle').click()
    await expect(gmPanel).toContainText('e2e-player: Cross bridge')
    await gmPanel.getByTestId('adventure-choice-gate-bridge_route').click()
    await expect(gmPanel.getByTestId('adventure-complete-bridge')).toBeVisible()
    await expect(gmPanel.getByTestId('adventure-complete-tunnel')).toHaveCount(0)
    await expect(gmPanel.getByTestId('adventure-choice-gate-tunnel_route')).toHaveCount(0)
    const projection = await (await request.get(`${path}/adventure`, { headers: { Authorization: `Bearer ${accessToken()}` } })).json()
    expect(projection.adventure.projection.progress.active_nodes).toEqual(['bridge'])
    expect(projection.adventure.projection.progress.selected_choices.gate).toBe('bridge_route')
    await player.reload()
    await player.getByTestId('adventure-panel-toggle').click()
    await expect(playerPanel).toContainText('已确认的选择: Cross bridge')
    await expect(playerPanel.getByTestId('adventure-choice-gate-bridge_route')).toHaveCount(0)
    await player.screenshot({ path: info.outputPath('player-choice.png'), fullPage: true })
  } finally { await playerContext.close() }
})
