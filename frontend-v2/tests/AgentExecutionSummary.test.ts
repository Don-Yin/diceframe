import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentExecutionSummary from '../src/components/assistant/AgentExecutionSummary.vue'

describe('AgentExecutionSummary', () => {
  it('renders generic batch targets, counts, and per-target execution statuses', () => {
    const wrapper = mount(AgentExecutionSummary, {
      props: {
        locale: 'zh-CN',
        approval: {
          approval_id: 'a-1',
          plan_digest: 'sha256:plan',
          tool: 'write_lorebook_entries',
          preview: {
            audience: 'gm',
            targets: [
              { id: 'book-1', label: '阿卡姆疑云', total: 4, changed_count: 2, affected_games: 3 },
              { id: 'book-2', label: '黄衣之王', total: 1, changed_count: 0, affected_games: 1 },
            ],
            summary: { total: 5, changed_count: 2, book_count: 2, affected_games: 4 },
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
        },
      },
    })

    expect(wrapper.get('[data-testid="agent-execution-summary"]').text()).toContain('阿卡姆疑云')
    expect(wrapper.text()).toContain('2')
    expect(wrapper.get('[data-testid="agent-execution-target-book-1"]').text()).toContain('已完成')
    expect(wrapper.get('[data-testid="agent-execution-target-book-2"]').text()).toContain('未执行')
  })
})
