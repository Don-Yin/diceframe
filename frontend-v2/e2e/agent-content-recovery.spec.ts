import type { APIResponse, Locator, Page } from '@playwright/test'
import { expect, test } from './fixtures'
import { accessToken } from './support'

const headers = () => ({ Authorization: `Bearer ${accessToken()}`, 'X-TRPG-Confirm': 'true' })
async function waitForWriteBudget(response: Pick<APIResponse, 'json'>) {
  const { retry_after } = await response.json()
  const seconds = Math.min(Math.max(Number(retry_after) || 1, 1), 60)
  test.info().setTimeout(test.info().timeout + seconds * 1000)
  await new Promise(resolve => setTimeout(resolve, seconds * 1000))
}
async function writeWithinBudget(write: () => Promise<APIResponse>) {
  let response = await write()
  for (let attempt = 0; response.status() === 429 && attempt < 3; attempt++) {
    await waitForWriteBudget(response)
    response = await write()
  }
  return response
}
// Keep the production write limit. Retry only an explicit 429, never an
// uncertain mutation outcome; the same pending UI approval remains in place.
async function clickWithinBudget(page: Page, button: Locator, endpoint: string, status = 200) {
  for (let attempt = 0; ; attempt++) {
    const responsePromise = page.waitForResponse(response => response.url().endsWith(endpoint) && response.request().method() === 'POST')
    await button.click()
    const response = await responsePromise
    if (response.status() !== 429 || attempt >= 3) {
      expect(response.status()).toBe(status)
      return response
    }
    await waitForWriteBudget(response)
  }
}
async function json(page: Page, url: string) {
  const response = await page.request.get(url, { headers: headers() })
  expect(response.ok()).toBe(true)
  return response.json()
}
async function confirmed(page: Page, tool: string, args: Record<string, unknown>) {
  const planResponse = await writeWithinBudget(() => page.request.post('/api/assistant/agent/plan', { headers: headers(), data: { tool, arguments: args } }))
  expect(planResponse.ok()).toBe(true)
  const plan = await planResponse.json()
  const response = await writeWithinBudget(() => page.request.post('/api/assistant/agent/confirm', { headers: headers(), data: {
    session_id: plan.session_id, approval_id: plan.approval.approval_id,
    plan_digest: plan.approval.plan_digest, approved: true,
  } }))
  expect(response.ok()).toBe(true)
  const result = await response.json()
  expect(result.ok).toBe(true)
  expect(result.result.ok).toBe(true)
  return result.result
}

test('GM can add a book after starting and keeps other games and round state intact', async ({ page }, info) => {
  const game = 'web|e2e-room|web_bot'
  const other = 'web|e2e-dnd2024|web_bot'
  const url = `/api/games/${encodeURIComponent(game)}`
  await page.goto(`/#/play?game=${encodeURIComponent(game)}&workbench=1`)
  const before = await json(page, url)
  const selectionBefore = await json(page, `${url}/lorebooks`)
  const originalIds = selectionBefore.books.filter((b: { selected: boolean; locked: boolean }) => b.selected && !b.locked).map((b: { id: string }) => b.id)
  const id = `agent-game-book-${info.project.name}`
  expect((await writeWithinBudget(() => page.request.post('/api/lorebooks', { headers: headers(), data: { id, name: '本局新增调查资料', enabled: true, language: 'zh-CN' } }))).ok()).toBe(true)
  // The shared catalogue includes the new book; editing this game's selection
  // must leave the other game's selection exactly as it was.
  const otherBefore = await json(page, `/api/games/${encodeURIComponent(other)}/lorebooks`)
  try {
    await page.getByTestId('gm-workspace').getByRole('tab', { name: '场景', exact: true }).click()
    await page.getByTestId('gm-game-lorebooks').click()
    const dialog = page.getByRole('dialog', { name: '本局资料册', exact: true })
    await dialog.getByRole('checkbox', { name: /本局新增调查资料/ }).check()
    await dialog.getByTestId('lorebook-save').click()
    await expect(dialog).toContainText('只影响本局')
    // Planning does not change bindings until the explicit confirmation.
    expect((await json(page, `${url}/lorebooks`)).books.find((b: { id: string }) => b.id === id).selected).toBe(false)
    await dialog.screenshot({ path: info.outputPath('game-lorebooks-confirm.png'), scale: 'css' })
    await dialog.getByTestId('lorebook-confirm').click()
    await expect(dialog).toHaveCount(0)
    await page.reload()
    await page.getByTestId('gm-workspace').getByRole('tab', { name: '场景', exact: true }).click()
    await page.getByTestId('gm-game-lorebooks').click()
    await expect(dialog.getByRole('checkbox', { name: /本局新增调查资料/ })).toBeChecked()
    await dialog.screenshot({ path: info.outputPath('game-lorebooks-selected.png'), scale: 'css' })
    const after = await json(page, url)
    expect(after.world_id).toBe(before.world_id)
    expect(after.round_number).toBe(before.round_number)
    expect(await json(page, `/api/games/${encodeURIComponent(other)}/lorebooks`)).toEqual(otherBefore)
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  } finally {
    await confirmed(page, 'set_game_lorebooks', { game_key: game, book_ids: originalIds })
    expect((await writeWithinBudget(() => page.request.delete(`/api/lorebooks/${id}`, { headers: headers() }))).ok()).toBe(true)
  }
})

test('content recovery undoes disable and restores archived private entries by server record', async ({ page }, info) => {
  await page.goto('/#/lorebook?world=freeform_sandbox')
  const book = `agent-recovery-${info.project.name}`
  const entry = `${book}-note`
  const endpoint = `/api/lorebooks/${book}/entries`
  expect((await writeWithinBudget(() => page.request.post('/api/lorebooks', { headers: headers(), data: { id: book, name: '可恢复的私人资料', enabled: true } }))).ok()).toBe(true)
  expect((await writeWithinBudget(() => page.request.post(endpoint, { headers: headers(), data: {
    id: entry, name: '调查线索', content: 'GM 私密：藏在书柜后的线索', visible_to: [], enabled: true,
  } }))).ok()).toBe(true)
  const original = (await json(page, endpoint)).entries.find((e: { id: string }) => e.id === entry)
  const dialog = page.getByRole('dialog', { name: '内容撤销 / 回收站', exact: true })
  const openRecovery = async () => { await page.getByTestId('content-recovery-open').click(); await expect(dialog).toBeVisible() }
  try {
    const disabled = await confirmed(page, 'set_lorebook_entries_enabled', { book_id: book, entry_ids: [entry], enabled: false })
    await openRecovery()
    await expect(dialog).not.toContainText('藏在书柜后的线索')
    await clickWithinBudget(page, dialog.getByTestId(`recovery-undo-${disabled.operation_id}`), '/api/assistant/agent/plan')
    expect((await json(page, endpoint)).entries.find((e: { id: string }) => e.id === entry).enabled).toBe(false)
    await clickWithinBudget(page, dialog.getByTestId('recovery-confirm'), '/api/assistant/agent/confirm')
    await expect(dialog).toHaveCount(0)
    expect((await json(page, endpoint)).entries.find((e: { id: string }) => e.id === entry).enabled).toBe(true)

    const archived = await confirmed(page, 'archive_lorebook_entries', { book_id: book, entry_ids: [entry] })
    expect((await json(page, endpoint)).entries.some((e: { id: string }) => e.id === entry)).toBe(false)
    await page.reload()
    await openRecovery()
    await clickWithinBudget(page, dialog.getByTestId(`recovery-restore-${archived.operation_id}`), '/api/assistant/agent/plan')
    await dialog.screenshot({ path: info.outputPath('content-restore-confirm.png'), scale: 'css' })
    await clickWithinBudget(page, dialog.getByTestId('recovery-confirm'), '/api/assistant/agent/confirm')
    await expect(dialog).toHaveCount(0)
    const restored = (await json(page, endpoint)).entries.find((e: { id: string }) => e.id === entry)
    for (const field of ['id', 'book_id', 'content', 'visible_to']) expect(restored[field]).toEqual(original[field])
    await openRecovery()
    await expect(dialog).toContainText('已恢复')
    await expect(dialog).not.toContainText('藏在书柜后的线索')
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
    await dialog.screenshot({ path: info.outputPath('content-recovery-history.png'), scale: 'css' })
    await dialog.getByTitle('关闭', { exact: true }).click()
    const changed = await confirmed(page, 'set_lorebook_entries_enabled', { book_id: book, entry_ids: [entry], enabled: false })
    await openRecovery()
    await clickWithinBudget(page, dialog.getByTestId(`recovery-undo-${changed.operation_id}`), '/api/assistant/agent/plan')
    expect((await writeWithinBudget(() => page.request.put(`${endpoint}/${entry}`, { headers: headers(), data: {
      name: original.name, content: '人工后续编辑', visible_to: [], enabled: false,
    } }))).ok()).toBe(true)
    const staleResponse = await clickWithinBudget(page, dialog.getByTestId('recovery-confirm'), '/api/assistant/agent/confirm', 400)
    expect((await staleResponse.json()).error).toMatch(/state changed|不会覆盖后续编辑/)
    await expect(dialog).toContainText('操作失败')
    expect((await json(page, endpoint)).entries.find((e: { id: string }) => e.id === entry).content).toBe('人工后续编辑')
    await clickWithinBudget(page, dialog.getByTestId('recovery-cancel'), '/api/assistant/agent/confirm')
    await expect(dialog).toHaveCount(0)
  } finally {
    expect((await writeWithinBudget(() => page.request.delete(`/api/lorebooks/${book}`, { headers: headers() }))).ok()).toBe(true)
  }
})
