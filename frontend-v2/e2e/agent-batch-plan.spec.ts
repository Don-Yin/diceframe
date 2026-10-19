import { expect, test } from './fixtures'

const SESSION_ID = '0123456789abcdef0123456789abcdef'
const APPROVAL_ID = 'abcdef0123456789abcdef0123456789'
const PLAN_DIGEST = `sha256:${'b'.repeat(64)}`

test('resumes a partial generic batch plan through /resume and keeps target report readable', async ({ page }) => {
  const approval = {
    approval_id: APPROVAL_ID,
    plan_digest: PLAN_DIGEST,
    tool: 'set_lorebooks_visibility',
    label: 'Write lorebook entries',
    resumable: true,
    execution_status: 'partial',
    expires_at: Math.floor(Date.now() / 1000) - 30 * 60,
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
    localStorage.setItem('diceframe_assistant_messages', JSON.stringify([{ role: 'user', content: '批量更新资料册' }, { role: 'assistant', content: '' }]))
  }, { sessionId: SESSION_ID })
  await page.route('**/api/assistant/agent/session/**', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ ok: true, session_id: SESSION_ID, pending: approval, drafts: {}, receipts: [], status: 'paused', authorization: null, task: { status: 'paused', completed_steps: 0, total_steps: 1 } }),
  }))
  await page.route('**/api/assistant/agent/capabilities*', route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, revision: 'batch-e2e', capabilities: [] }),
  }))
  let resumeBody: Record<string, unknown> | undefined
  await page.route('**/api/assistant/agent/resume*', async route => {
    resumeBody = route.request().postDataJSON()
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ ok: true, result: { status: 'completed', success_count: 2, failed_count: 0, not_executed_count: 0, changed_count: 2, targets: [
        { id: 'book-1', label: '阿卡姆疑云', status: 'succeeded', changed_count: 2 },
        { id: 'book-2', label: '黄衣之王', status: 'succeeded', changed_count: 0 },
      ] }, pending: null }),
    })
  })
  await page.route('**/api/assistant/agent/confirm*', route => route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'confirm should not be called for resume' }) }))

  await page.goto('/#/overview?game=game-1')
  await page.getByTestId('assistant-shell-fab').click()
  await expect(page.locator('[data-agent-approval]')).toBeVisible()
  await expect(page.getByTestId('agent-execution-summary')).toContainText('阿卡姆疑云')
  await expect(page.getByTestId('agent-execution-target-book-2')).toContainText('未执行')
  await expect(page.getByTestId('agent-resume')).toBeEnabled()
  await page.getByTestId('agent-resume').click()
  await expect.poll(() => resumeBody).toMatchObject({ session_id: SESSION_ID, approval_id: approval.approval_id, plan_digest: approval.plan_digest })
  await expect(page.locator('[data-agent-approval]')).toHaveCount(0)
  await expect(page.getByTestId('assistant-actions')).toContainText('执行计划已完成')
  await expect(page.getByTestId('assistant-actions')).toContainText('成功 2')
})

test('confirms one public twenty-lorebook plan and keeps the target list inside the task workspace', async ({ page }) => {
  const targets = Array.from({ length: 20 }, (_, index) => ({
    id: `${index + 1}`.padStart(32, '0'),
    label: `公开资料册 ${index + 1}`,
    total: 12,
    changed_count: 4,
    affected_games: ['game-public'],
  }))
  const approval = {
    approval_id: '1234567890abcdef1234567890abcdef',
    plan_digest: `sha256:${'c'.repeat(64)}`,
    tool: 'set_lorebooks_visibility',
    label: 'Set lorebook visibility',
    preview: {
      audience: 'public',
      targets,
      total: 240,
      changed_count: 80,
      book_count: targets.length,
      affected_games: ['game-public'],
    },
  }
  const completedTargets = targets.map(target => ({ ...target, status: 'succeeded', operation_ids: [`${target.id.slice(0, 16)}0000000000000000`] }))
  await page.addInitScript(({ sessionId }) => {
    localStorage.setItem('diceframe_assistant_session_id', sessionId)
    localStorage.setItem('diceframe_assistant_messages', JSON.stringify([{ role: 'user', content: '公开二十册资料' }, { role: 'assistant', content: '' }]))
  }, { sessionId: SESSION_ID })
  await page.route('**/api/assistant/agent/session/**', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ ok: true, session_id: SESSION_ID, pending: approval, drafts: {}, receipts: [], status: 'approval_required', authorization: null, task: { status: 'approval_required', completed_steps: 0, total_steps: 1 } }),
  }))
  await page.route('**/api/assistant/agent/capabilities*', route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, revision: 'batch-e2e', capabilities: [] }),
  }))
  let confirmCount = 0
  await page.route('**/api/assistant/agent/confirm*', async route => {
    confirmCount += 1
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ ok: true, result: {
        status: 'completed', success_count: targets.length, failed_count: 0, not_executed_count: 0, changed_count: 80,
        targets: completedTargets,
      }, pending: null }),
    })
  })

  await page.goto('/#/overview?game=game-public')
  await page.getByTestId('assistant-shell-fab').click()
  const summary = page.getByTestId('agent-execution-summary')
  await expect(summary).toBeVisible()
  await expect(summary).toContainText('公开')
  await expect(summary.locator('[data-testid^="agent-execution-target-"]')).toHaveCount(20)
  const targetList = summary.locator('.agent-execution-targets ul')
  await expect(targetList).toBeVisible()
  const layoutBefore = await page.locator('.assistant-panel').evaluate(panel => {
    const workspace = panel.querySelector('.assistant-workspace-body') as HTMLElement | null
    const targetListElement = panel.querySelector('.agent-execution-targets ul') as HTMLElement | null
    return {
      panelOverflow: panel.scrollWidth - panel.clientWidth,
      workspaceOverflow: workspace ? workspace.scrollWidth - workspace.clientWidth : 0,
      targetListOverflow: targetListElement ? targetListElement.scrollHeight - targetListElement.clientHeight : 0,
      viewportOverflow: document.documentElement.scrollWidth - window.innerWidth,
    }
  })
  expect(layoutBefore.panelOverflow).toBeLessThanOrEqual(1)
  expect(layoutBefore.workspaceOverflow).toBeLessThanOrEqual(1)
  expect(layoutBefore.targetListOverflow).toBeGreaterThan(0)
  expect(layoutBefore.viewportOverflow).toBeLessThanOrEqual(1)

  await page.getByRole('button', { name: '确认执行' }).click()
  await expect.poll(() => confirmCount).toBe(1)
  await expect(page.locator('[data-agent-approval]')).toHaveCount(0)
  const finalSummary = page.getByTestId('assistant-actions').getByTestId('agent-execution-summary')
  await expect(finalSummary).toContainText('执行计划已完成')
  await expect(finalSummary).toContainText('成功 20')
  await expect(finalSummary).toContainText('未执行 0')
})

test('keeps an initially expired approval disabled instead of treating it as resumable', async ({ page }) => {
  const approval = {
    approval_id: 'fedcba9876543210fedcba9876543210',
    plan_digest: `sha256:${'d'.repeat(64)}`,
    tool: 'set_lorebooks_visibility',
    label: 'Set lorebook visibility',
    expires_at: Math.floor(Date.now() / 1000) - 30 * 60,
    preview: {
      audience: 'public',
      targets: [{ id: 'book-expired', label: '已过期资料册', total: 1, changed_count: 1 }],
    },
  }
  await page.addInitScript(({ sessionId }) => {
    localStorage.setItem('diceframe_assistant_session_id', sessionId)
    localStorage.setItem('diceframe_assistant_messages', JSON.stringify([{ role: 'user', content: '执行已过期计划' }, { role: 'assistant', content: '' }]))
  }, { sessionId: SESSION_ID })
  await page.route('**/api/assistant/agent/session/**', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ ok: true, session_id: SESSION_ID, pending: approval, drafts: {}, receipts: [], status: 'approval_required', authorization: null, task: { status: 'approval_required', completed_steps: 0, total_steps: 1 } }),
  }))
  await page.route('**/api/assistant/agent/capabilities*', route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, revision: 'batch-e2e', capabilities: [] }),
  }))

  await page.goto('/#/overview?game=game-public')
  await page.getByTestId('assistant-shell-fab').click()
  await expect(page.locator('[data-agent-approval]')).toBeVisible()
  await expect(page.getByRole('button', { name: '确认执行' })).toBeDisabled()
  await expect(page.getByTestId('agent-resume')).toHaveCount(0)
})
