import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { expect, test } from './fixtures'
import { accessToken } from './support'

test('AI import shows progress, cancels the provider call, then reviews and saves a draft', async ({ page, request }, info) => {
  test.setTimeout(90_000)
  let calls = 0, cancelled = 0
  const model = createServer(async (req, res) => {
    let body = ''
    for await (const chunk of req) body += chunk
    const input = JSON.parse(body)
    const data = JSON.parse(input.messages.at(-1).content)
    calls++
    if (calls === 1) {
      res.on('close', () => { cancelled++ })
      return
    }
    const output = data.source_units ? {
      scenes: [
        { name: '整理后的入口', chapter: '第一章', description: '守门人等待冒险者。', source_ids: data.source_units.map((unit: { id: string }) => unit.id), npc_names: [] },
        { name: '进入大厅', chapter: '第一章', description: '队伍进入大厅。', source_ids: data.source_units.map((unit: { id: string }) => unit.id), npc_names: [] },
      ], resources: [],
    } : { start_ids: [data.scenes[0].id], links: [{ from: data.scenes[0].id, to: data.scenes[1].id, label: '' }] }
    res.setHeader('Content-Type', 'application/json')
    res.end(JSON.stringify({ choices: [{ message: { role: 'assistant', content: JSON.stringify(output) }, finish_reason: 'stop' }], usage: { total_tokens: 100 } }))
  })
  await new Promise<void>(resolve => model.listen(0, '127.0.0.1', resolve))
  const port = (model.address() as AddressInfo).port
  const headers = { Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' }
  const config = await (await request.get('/api/config', { headers })).json()
  try {
    const providers = config.ai_providers.map((provider: { id: string }) => provider.id === config.llm_provider_ref
      ? { ...provider, base_url: `http://127.0.0.1:${port}/v1` } : provider)
    expect((await request.post('/api/config', { headers, data: { ai_providers: providers } })).ok()).toBe(true)
    const title = `AI 导入 ${info.project.name}`
    await page.goto('/#/adventures')
    await page.locator('.adventure-header-more > summary').click()
    await page.getByRole('button', { name: '导入剧本 / 外部模组', exact: true }).click()
    await page.locator('.script-review input[type=file]').setInputFiles({ name: 'ai-import.md', mimeType: 'text/markdown', buffer: Buffer.from(`# ${title}\n### 开场\n守门人等待冒险者，队伍随后进入大厅。`) })
    await page.getByTestId('script-preview').click()
    await expect(page.getByTestId('graph-name')).toHaveValue(title)
    await expect(page.getByTestId('script-ai-start')).toBeDisabled()
    await expect(page.getByTestId('script-ai-organizer')).toContainText('消耗模型 token')
    await page.getByTestId('script-ai-consent').check()
    await page.getByTestId('script-ai-start').click()
    await expect(page.getByTestId('script-ai-organizer')).toContainText('正在整理第 1 / 1 段')
    await expect(page.getByRole('progressbar')).toBeVisible()
    await expect.poll(() => calls).toBe(1)
    await page.getByTestId('script-ai-organizer').screenshot({ path: info.outputPath('ai-progress.png') })
    await page.getByTestId('script-ai-cancel').click()
    await expect(page.getByTestId('script-ai-organizer')).toContainText('已取消，原草稿未被替换')
    await expect.poll(() => cancelled).toBe(1)
    await expect(page.locator('.graph-node')).toHaveCount(1)
    await page.getByTestId('script-ai-start').click()
    await expect(page.getByTestId('script-ai-result')).toContainText('剧情场景：2')
    await page.getByTestId('script-ai-result').locator('summary').click()
    await expect(page.getByTestId('script-ai-result')).toContainText('整理后的入口')
    await expect(page.locator('.graph-node')).toHaveCount(1)
    await page.getByTestId('script-ai-organizer').screenshot({ path: info.outputPath('ai-result.png') })
    await page.getByTestId('script-ai-apply').click()
    await expect(page.locator('.graph-node')).toHaveCount(3)
    await expect(page.getByTestId('script-publish')).toBeDisabled()
    await page.getByTestId('script-reviewed').check()
    await expect(page.getByTestId('script-publish')).toBeEnabled()
    const committed = page.waitForResponse(response => response.url().endsWith('/adventures/script/commit'))
    await page.getByTestId('script-publish').click()
    const result = await (await committed).json()
    expect(result.ok, JSON.stringify(result)).toBe(true)
    const detail = await (await request.get(`/api/adventures/${encodeURIComponent(result.adventure_id)}`, { headers })).json()
    const nodes = detail.adventure.files['adventure.json'].nodes
    expect(nodes[0].name).toBe('整理后的入口')
    expect(nodes[2].description).toContain('守门人等待冒险者，队伍随后进入大厅')
    expect(nodes.every((node: { visibility: string }) => node.visibility === 'gm')).toBe(true)
    expect(calls).toBe(3)
  } finally {
    await request.post('/api/config', { headers, data: { ai_providers: config.ai_providers } })
    model.closeAllConnections()
    await new Promise<void>(resolve => model.close(() => resolve()))
  }
})
