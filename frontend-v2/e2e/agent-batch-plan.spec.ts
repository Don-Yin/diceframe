import { expect, test } from './fixtures'

const SESSION_ID = 'batch-session-0123456789abcdef0123456789abcdef'

test('resumes a partial generic batch plan through /resume and keeps target report readable', async ({ page }) => {
  const approval = {
    approval_id: 'batch-approval-0123456789abcdef',
    plan_digest: 'sha256:batch-plan',
    tool: 'write_lorebook_entries',
    label: 'Write lorebook entries',
    resumable: true,
    execution_status: 'partial',
    preview: {
      audience: 'gm',
      targets: [
        { id: 'book-1', label: '阿卡姆疑云', total: 4, changed_count: 2, affected_games: ['game-1'] },
        { id: 'book-2', label: '黄衣之王', total: 2, changed_count: 0, affected_games: ['game-1'] },
      ],
      total: 6,
      changed_count: 2,
      book_count: 2,
      affected_games: ['game-1'],
    },
    execution_state: {
      report: {
        status: 'partial', success_count: 1, failed_count: 0, not_executed_count: 1, changed_count: 2,
        targets: [
          { id: 'book-1', label: '阿卡姆疑云', status: 'succeeded', changed_count: 2, operation_ids: ['op-1'] },
          { id: 'book-2', label: '黄衣之王', status: 'not_executed', changed_count: 0, operation_ids: [] },
        ],
      },
    },
  }
  await page.addInitScript(({ sessionId }) => {
    localStorage.setItem('diceframe_assistant_session_id', sessionId)
    localStorage.setItem('diceframe_assistant_messages', JSON.stringify([{ role: 'user', content: '批量更新资料册' }]))
  }, { sessionId: SESSION_ID })
  await page.route('**/api/assistant/agent/session/**', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ ok: true, session_id: SESSION_ID, pending: approval, drafts: {}, receipts: [], status: 'paused', authorization: null, task: { status: 'paused', completed_steps: 0, total_steps: 1 } }),
  }))
  await page.route('**/api/assistant/agent/capabilities*', route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, revision: 'batch-e2e', capabilities: [] }),
  }))
  let resumeBody: Record<string, unknown> | undefined
  await page.route('**/api/assistant/agent/resume', async route => {
    resumeBody = route.request().postDataJSON()
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ ok: true, result: { status: 'completed', success_count: 2, failed_count: 0, not_executed_count: 0, changed_count: 2, targets: [
        { id: 'book-1', label: '阿卡姆疑云', status: 'succeeded', changed_count: 2 },
        { id: 'book-2', label: '黄衣之王', status: 'succeeded', changed_count: 0 },
      ] }, pending: null }),
    })
  })
  await page.route('**/api/assistant/agent/confirm', route => route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'confirm should not be called for resume' }) }))

  await page.goto('/#/overview?game=game-1')
  await page.getByTestId('assistant-shell-fab').click()
  await expect(page.locator('[data-agent-approval]')).toBeVisible()
  await expect(page.getByTestId('agent-execution-summary')).toContainText('阿卡姆疑云')
  await expect(page.getByTestId('agent-execution-target-book-2')).toContainText('未执行')
  await page.getByTestId('agent-resume').click()
  await expect.poll(() => resumeBody).toMatchObject({ session_id: SESSION_ID, approval_id: approval.approval_id, plan_digest: approval.plan_digest })
  await expect(page.locator('[data-agent-approval]')).toHaveCount(0)
  await expect(page.getByTestId('assistant-actions')).toContainText('阿卡姆疑云')
  await expect(page.getByTestId('assistant-actions')).toContainText('已完成')
})
