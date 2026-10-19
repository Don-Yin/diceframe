import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentTaskCard from '../src/components/assistant/AgentTaskCard.vue'

describe('AgentTaskCard', () => {
  it('edits real ContentReview draft items and preserves source identity', async () => {
    const wrapper = mount(AgentTaskCard, {
      props: {
        draft: {
          draft_id: 'd-1',
          review: { ok: true, draft: { source_id: 'src-1', filename: 'draft.json', language: 'zh-CN', items: [{ id: 'item-1', name: 'Old', text: 'Body', target: 'world', references: [] }] } },
        },
      },
    })
    const inputs = wrapper.findAll('input, textarea, select')
    expect(inputs).toHaveLength(3)
    expect(wrapper.text()).toContain('World')
    expect(wrapper.text()).not.toContain('draft.json')
    expect(wrapper.text()).not.toContain('d-1')
    await inputs[0].setValue('New')
    expect(wrapper.find('[data-agent-edited]').exists()).toBe(true)
    expect(wrapper.get('[data-agent-save]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Edited')
    await wrapper.get('[data-agent-review]').trigger('click')
    expect(wrapper.emitted('review')?.[0]).toEqual([{
      draft_id: 'd-1',
      draft: { source_id: 'src-1', filename: 'draft.json', language: 'zh-CN', items: [{ id: 'item-1', name: 'New', text: 'Body', target: 'world', references: [] }] },
    }])
  })

  it('disables actions while busy and for an unreviewed draft', () => {
    const wrapper = mount(AgentTaskCard, {
      props: {
        busy: true,
        streaming: true,
        draft: { draft_id: 'd-2', review: { ok: false, blockers: ['missing target'], draft: { source_id: 'src-2', filename: 'x', language: 'en', items: [{ id: 'i', name: 'n', text: 't', target: 'world' }] } } },
      },
    })
    expect(wrapper.get('[data-agent-review]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-agent-save]').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('input, textarea, select').every(control => control.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.text()).toContain('missing target')
  })
})
