import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api, submitRulesetIntent } = vi.hoisted(() => ({
  api: vi.fn(),
  submitRulesetIntent: vi.fn(),
}))

vi.mock('../src/api/client', () => ({ api }))
vi.mock('../src/api/rulesets', () => ({ submitRulesetIntent }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import AdventurePanel from '../src/components/play/AdventurePanel.vue'
import { i18n } from '../src/i18n'

const suggestion = {
  proposal_id: 'proposal-1',
  node_id: 'gate',
  reason: '队伍已经找到钥匙并打开大门。',
  evidence_rounds: [1],
}
const secondSuggestion = {
  ...suggestion,
  proposal_id: 'proposal-2',
  node_id: 'gate-2',
  reason: '队伍已经完成第二道门。',
}

function response(withSuggestion = true) {
  return {
    ok: true,
    adventure: {
      binding: { adventure_id: 'test:adventure', version: '1.0.0' },
      available: true,
      format: 'diceframe:adventure-graph-v2',
      projection: {
        chapters: [{ id: 'chapter', name: '第一章' }],
        nodes: [{ id: 'gate', type: 'scene', chapter_id: 'chapter', name: '石门' }],
        objectives: [],
        milestones: [],
        progress: {
          active_nodes: ['gate'],
          completion_suggestions: withSuggestion ? [suggestion] : [],
        },
      },
    },
  }
}

function responseWithSuggestions(suggestions: typeof suggestion[]) {
  const value = response(false)
  value.adventure.projection.progress.completion_suggestions = suggestions
  return value
}

let wrappers: ReturnType<typeof mount>[] = []

describe('AdventurePanel completion reminders', () => {
  beforeEach(() => {
    localStorage.clear()
    i18n.global.locale.value = 'zh-CN'
    submitRulesetIntent.mockReset()
    submitRulesetIntent.mockResolvedValue({ ok: true })
    api.mockReset()
    api.mockImplementation(async (_path: string, _options?: unknown) => response(true))
  })

  afterEach(() => {
    wrappers.forEach(wrapper => wrapper.unmount())
    wrappers = []
    document.body.innerHTML = ''
  })

  it('keeps a badge after closing the floating notice and lets the GM ignore the pending suggestion', async () => {
    let dismissed = false
    api.mockImplementation(async (_path: string, _options?: unknown) => response(!dismissed))
    submitRulesetIntent.mockImplementation(async (_gameKey: string, intent: { type: string }) => {
      if (intent.type === 'adventure.completion_suggestion.dismiss') dismissed = true
      return { ok: true }
    })

    const wrapper = mount(AdventurePanel, {
      attachTo: document.body,
      props: { gameKey: 'web|room|bot', isGm: true },
      global: { plugins: [i18n] },
    })
    wrappers.push(wrapper)
    await flushPromises()

    expect(wrapper.get('[data-testid="adventure-suggestion-badge"]').text()).toBe('1')
    expect(document.body.querySelector('[data-testid="adventure-suggestion-toast"]')).toBeTruthy()
    ;(document.body.querySelector('[data-testid="adventure-suggestion-toast-close"]') as HTMLButtonElement).click()
    await flushPromises()
    expect(wrapper.element.querySelector('[data-testid="adventure-suggestion-badge"]')).toBeTruthy()

    await wrapper.get('[data-testid="adventure-panel-toggle"]').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain(suggestion.reason)
    ;(document.body.querySelector('[data-testid="adventure-suggestion-ignore"]') as HTMLButtonElement).click()
    await flushPromises()

    expect(submitRulesetIntent).toHaveBeenCalledWith('web|room|bot', {
      type: 'adventure.completion_suggestion.dismiss',
      proposal_id: suggestion.proposal_id,
    })
    expect(wrapper.element.querySelector('[data-testid="adventure-suggestion-badge"]')).toBeNull()
  })

  it('never renders GM completion reminders in the player view', async () => {
    const wrapper = mount(AdventurePanel, {
      props: { gameKey: 'web|room|bot', isGm: false },
      global: { plugins: [i18n] },
    })
    wrappers.push(wrapper)
    await flushPromises()

    expect(wrapper.element.querySelector('[data-testid="adventure-suggestion-badge"]')).toBeNull()
    expect(document.body.querySelector('[data-testid="adventure-suggestion-toast"]')).toBeNull()
  })

  it('shows the next reminder after the current toast is closed', async () => {
    api.mockImplementation(async () => responseWithSuggestions([suggestion, secondSuggestion]))

    const wrapper = mount(AdventurePanel, {
      attachTo: document.body,
      props: { gameKey: 'web|room|bot', isGm: true },
      global: { plugins: [i18n] },
    })
    wrappers.push(wrapper)
    await flushPromises()

    expect(document.body.textContent).toContain('检查“石门”')
    ;(document.body.querySelector('[data-testid="adventure-suggestion-toast-close"]') as HTMLButtonElement).click()
    await flushPromises()

    expect(document.body.querySelector('[data-testid="adventure-suggestion-toast"]')?.getAttribute('data-proposal-id'))
      .toBe('proposal-2')
  })
})
