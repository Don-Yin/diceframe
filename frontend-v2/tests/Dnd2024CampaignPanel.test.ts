import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), submit: vi.fn(), locale: 'en' }))

vi.mock('../src/features/rulesets/dnd2024/api', () => ({
  fetchRulesetAvailableActions: mocks.fetch,
  submitRulesetIntent: mocks.submit,
}))
vi.mock('../src/composables/useLocale', () => ({
  useLocale: () => ({ locale: ref(mocks.locale) }),
}))

import Dnd2024CampaignPanel from '../src/features/rulesets/dnd2024/campaign/Dnd2024CampaignPanel.vue'

const defaults = {
  tone: 'Heroic adventure', difficulty: 'standard', content_rating: 'teen',
  session_length_minutes: 120, pvp_policy: 'consent', safety_tool: 'pause_and_check',
  lines: [], veils: [], table_rules: ['Share spotlight'], coach_enabled: true,
}

function response(state: 'new' | 'pending' | 'tutorial' = 'new') {
  const locked = state === 'tutorial'
  return {
    ok: true, game_key: 'web|campaign|bot', rule_id: 'dnd2024_srd',
    ruleset_runtime: {
      id: 'core:dnd2024', version: 1, requested_minimum_version: 1,
      capabilities: {
        experience_profile: 'dnd2024', character_builder: 'professional',
        character_lifecycle: 'rules_aware',
        authoritative_intents: true, deterministic_combat: true,
        versioned_state: true, session_zero: true, tutorial_coach: true,
      },
    },
    gameplay: {
      state_schema_version: 1, state_version: state === 'new' ? 0 : 1,
      combat: {
        status: 'none', round: 0, turn_index: 0, current_actor_id: '', initiative: [],
        position_mode: 'theater', economy: {}, reactions: {}, pending_decisions: [], actors: [],
      },
      encounter_presets: [],
      campaign: {
        automation: { mode: locked ? 'assist' : 'auto' },
        session_zero_defaults: defaults,
        session_zero: {
          status: locked ? 'locked' : state, revision: state === 'new' ? 0 : 1,
          agreement: locked ? defaults : null,
          pending_agreement: state === 'pending' ? defaults : null,
          responses: {},
        },
        proposals: [], entities: { task: [], clue: [], fact: [], item: [], relationship: [] },
        chapter_summaries: [],
        tutorial: {
          status: locked ? 'active' : 'not_started', coach_enabled: true,
          adventure: { id: 'lanterns_of_greymoor', name: 'Lost Lanterns', summary: 'Starter', estimated_minutes: 90, chapter_count: 3 },
          requirement_met: false, history: [], hints_used: {},
          current_step: locked ? {
            id: 'thorn_ambush', chapter_id: 'thorn_glade', title: 'First Encounter',
            narration: 'A goblin appears.', objective: 'Finish combat.', hint: 'Move or shoot.',
            requires: 'combat_ended', encounter_preset_id: 'first_skirmish',
            choices: [{ id: 'secure_the_glade', label: 'Search', description: 'Search after combat.', next_step_id: 'restore' }],
          } : null,
        },
      },
    },
    available_actions: state === 'new' ? [{
      type: 'session_zero.propose', label: 'Propose', expected_version: 0, defaults,
    }] : state === 'pending' ? [{
      type: 'session_zero.respond', label: 'Respond', expected_version: 1, options: ['accept', 'request_changes'],
    }] : [{
      type: 'tutorial.choose', label: 'Choose', expected_version: 1,
      choice_ids: ['secure_the_glade'], requirement_met: false,
    }, {
      type: 'tutorial.hint', label: 'Hint', expected_version: 1,
    }, {
      type: 'tutorial.coach.set', label: 'Coach', expected_version: 1,
    }],
  }
}

describe('D&D 2024 campaign panel', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mocks.locale = 'en'
    mocks.fetch.mockReset().mockResolvedValue(response('new'))
    mocks.submit.mockReset().mockResolvedValue(response('pending'))
  })

  it('creates a Session 0 proposal without silently locking it', async () => {
    const wrapper = mount(Dnd2024CampaignPanel, {
      props: { gameKey: 'web|campaign|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()
    const textareas = wrapper.findAll('textarea')
    await textareas[0].setValue('Body horror\nChild harm')
    await wrapper.get('.agreement-grid .campaign-primary').trigger('click')
    await flushPromises()

    expect(mocks.submit).toHaveBeenCalledOnce()
    expect(mocks.submit.mock.calls[0][1]).toMatchObject({
      type: 'session_zero.propose', expected_version: 0,
      agreement: { lines: ['Body horror', 'Child harm'] },
    })
    expect(mocks.submit.mock.calls[0][1].type).not.toBe('session_zero.lock')
    wrapper.unmount()
  })

  it('offers a one-click recommended start for a solo beginner', async () => {
    const initial = response('new')
    ;(initial.available_actions as unknown as Array<Record<string, unknown>>).unshift({
      type: 'session_zero.quick_start', label: 'Quick start', expected_version: 0,
    })
    mocks.fetch.mockResolvedValueOnce(initial)
    mocks.submit.mockResolvedValueOnce(response('tutorial'))
    const wrapper = mount(Dnd2024CampaignPanel, {
      props: { gameKey: 'web|campaign|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('First game? Start in one minute')
    await wrapper.get('.quick-start-card .campaign-primary').trigger('click')
    await flushPromises()

    expect(mocks.submit.mock.calls[0][1]).toMatchObject({
      type: 'session_zero.quick_start', expected_version: 0,
    })
    wrapper.unmount()
  })

  it('localizes stable campaign values and default table rules in Chinese', async () => {
    mocks.locale = 'zh-CN'
    const localized = response('tutorial')
    const campaign = localized.gameplay.campaign as unknown as {
      proposals: Array<Record<string, unknown>>
      entities: Record<string, Array<Record<string, unknown>>>
    }
    campaign.proposals = [{
      proposal_id: 'p1', entity_id: 'task:test', kind: 'task', title: '寻找灯火',
      summary: '查清熄灯原因。', visibility: 'public', status: 'pending',
    }]
    campaign.entities.task = [{
      id: 'task:test', kind: 'task', title: '寻找灯火', summary: '查清熄灯原因。',
      visibility: 'public', status: 'confirmed',
    }]
    mocks.fetch.mockResolvedValueOnce(localized)
    const wrapper = mount(Dnd2024CampaignPanel, {
      props: { gameKey: 'web|campaign|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    const selects = wrapper.findAll('.agreement-grid select')
    expect(selects[0].text()).toContain('英雄冒险，保留轻松幽默')
    expect(selects[1].text()).toContain('剧情优先')
    expect(selects[1].text()).not.toContain('Story')
    expect(selects[2].text()).toContain('青少年')
    expect(selects[3].text()).toContain('仅经同意')
    expect((wrapper.findAll('.agreement-grid textarea')[2].element as HTMLTextAreaElement).value).toContain('让每位玩家都有表现机会')
    expect(wrapper.text()).toContain('任务 · 全员可见')
    expect(wrapper.text()).toContain('已确认')
    expect(wrapper.text()).toContain('第二章：荆棘林地')
    wrapper.unmount()
  })

  it('keeps a compact adventure status and removes the new-player lesson card', async () => {
    mocks.locale = 'zh-CN'
    mocks.fetch.mockResolvedValueOnce(response('tutorial'))
    const wrapper = mount(Dnd2024CampaignPanel, {
      props: { gameKey: 'web|campaign|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    const adventure = wrapper.get('.adventure-card')
    const records = wrapper.get('.records-card')
    expect(adventure.get('.adventure-status').text()).toContain('当前目标')
    expect(adventure.text()).not.toContain('你不需要先学完整规则')
    expect(adventure.text()).not.toContain('你是谁')
    expect(adventure.text()).not.toContain('看不懂，给我提示')
    expect(adventure.find('.step-card').exists()).toBe(false)
    expect(adventure.element.compareDocumentPosition(records.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(wrapper.find('.composer').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps narrative input out of the campaign toolbox', async () => {
    mocks.locale = 'zh-CN'
    const notStarted = response('tutorial')
    notStarted.gameplay.campaign.tutorial.status = 'not_started'
    notStarted.gameplay.campaign.tutorial.current_step = null
    notStarted.available_actions = [{
      type: 'tutorial.start', label: 'Start', expected_version: 1,
    }]
    mocks.fetch.mockResolvedValueOnce(notStarted)
    const wrapper = mount(Dnd2024CampaignPanel, {
      props: { gameKey: 'web|campaign|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    expect(wrapper.find('.adventure-composer').exists()).toBe(false)
    expect(wrapper.find('.composer').exists()).toBe(false)
    expect(wrapper.get('.adventure-card .campaign-primary').text()).toContain('进入当前冒险')
    wrapper.unmount()
  })

  it('lets a player explicitly accept the current revision', async () => {
    mocks.fetch.mockResolvedValueOnce(response('pending'))
    const wrapper = mount(Dnd2024CampaignPanel, {
      props: { gameKey: 'web|campaign|bot', actorId: 'ally', isGm: false },
    })
    await flushPromises()
    await wrapper.get('.response-area .campaign-primary').trigger('click')
    await flushPromises()

    expect(mocks.submit.mock.calls[0][1]).toMatchObject({
      type: 'session_zero.respond', response: 'accept', expected_version: 1,
    })
    wrapper.unmount()
  })

  it('keeps only a collapsed GM recovery path when automation cannot advance', async () => {
    mocks.fetch.mockResolvedValueOnce(response('tutorial'))
    mocks.submit.mockResolvedValue(response('tutorial'))
    const wrapper = mount(Dnd2024CampaignPanel, {
      props: { gameKey: 'web|campaign|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    expect(wrapper.get('.adventure-status').text()).toContain('Current objective')
    expect(wrapper.get('.gm-fallback').attributes('open')).toBeUndefined()
    expect(wrapper.get('.gm-fallback .choice-grid button').attributes('disabled')).toBeDefined()
    expect(mocks.submit).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('Move or shoot.')
    wrapper.unmount()
  })

  it('moves the player to authoritative combat when a tutorial choice reaches an encounter', async () => {
    const beforeEncounter = response('tutorial')
    beforeEncounter.gameplay.campaign.tutorial.requirement_met = true
    mocks.fetch.mockResolvedValueOnce(beforeEncounter)
    mocks.submit.mockResolvedValue(response('tutorial'))
    const wrapper = mount(Dnd2024CampaignPanel, {
      props: { gameKey: 'web|campaign|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    await wrapper.get('.gm-fallback .choice-grid button').trigger('click')
    await flushPromises()

    expect(mocks.submit.mock.calls[0][1]).toMatchObject({ type: 'tutorial.choose' })
    expect(wrapper.emitted('navigate')).toEqual([['combat']])
    wrapper.unmount()
  })

  it('lets the GM persist a shared AI GM automation mode', async () => {
    const initial = response('tutorial') as any
    initial.gameplay.campaign.automation = { mode: 'assist' }
    initial.available_actions.push({
      type: 'automation.set', label: 'Set automation', expected_version: 1,
      options: ['auto', 'assist', 'manual'], current: 'assist',
    })
    mocks.fetch.mockResolvedValueOnce(initial)
    mocks.submit.mockResolvedValueOnce(initial)
    const wrapper = mount(Dnd2024CampaignPanel, {
      props: { gameKey: 'web|campaign|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    expect(wrapper.get('.automation-card summary').text()).toContain('Assist')
    await wrapper.findAll('.automation-options button')[2].trigger('click')
    await flushPromises()
    expect(mocks.submit.mock.calls[0][1]).toMatchObject({
      type: 'automation.set', mode: 'manual', expected_version: 1,
    })
    wrapper.unmount()
  })

  it('renders standard free play without tutorial controls or shared-log intents', async () => {
    const sandbox = response('tutorial')
    sandbox.gameplay.campaign.tutorial = {
      status: 'unavailable', coach_enabled: false, adventure: {},
      requirement_met: false, history: [], hints_used: {}, current_step: null,
    } as any
    sandbox.available_actions = []
    mocks.fetch.mockResolvedValueOnce(sandbox)
    const wrapper = mount(Dnd2024CampaignPanel, {
      props: {
        gameKey: 'web|campaign|bot', actorId: 'gm', isGm: true,
        worldName: 'Selected Worldbook',
      },
    })
    await flushPromises()

    expect(wrapper.get('.campaign-head').text()).toContain('Advanced rules · Standard mode')
    expect(wrapper.get('.sandbox-card').text()).toContain('shared action composer')
    expect(wrapper.get('.sandbox-card').text()).toContain('Selected Worldbook')
    expect(wrapper.find('.adventure-card').exists()).toBe(false)
    expect(wrapper.find('.composer').exists()).toBe(false)
    expect(mocks.submit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps the professional adventure connected to the shared scene map', async () => {
    mocks.fetch.mockResolvedValueOnce(response('tutorial'))
    const wrapper = mount(Dnd2024CampaignPanel, {
      props: {
        gameKey: 'web|campaign|bot', actorId: 'gm', isGm: true,
        worldName: '灰沼边境', sceneName: '灰沼驿道',
        map: {
          active_map: { id: 'map-1', name: '灰沼驿道地图', mode: 'graph' },
          current_location_id: 'road',
          locations: [{ id: 'road', name: '驿道入口' }],
        },
      },
    })
    await flushPromises()

    expect(wrapper.get('.shared-context').text()).toContain('灰沼边境')
    expect(wrapper.get('.shared-context').text()).toContain('驿道入口')
    await wrapper.get('.shared-context button').trigger('click')
    expect(wrapper.emitted('open-map')).toEqual([[]])
    wrapper.unmount()
  })

  it('keeps multiplayer branch choices out of the player toolbox', async () => {
    const multiplayer = response('tutorial') as any
    multiplayer.gameplay.campaign.tutorial.requirement_met = true
    multiplayer.gameplay.campaign.tutorial.current_step.choices = [
      { id: 'inspect_cold_ash', label: 'Inspect ash', description: 'Look closer.', next_step_id: 'keepers_plea' },
      { id: 'check_wagon_tracks', label: 'Check tracks', description: 'Search the wagon.', next_step_id: 'keepers_plea' },
    ]
    multiplayer.gameplay.campaign.party_decision = {
      status: 'open', step_id: 'mistbound_road',
      choices: multiplayer.gameplay.campaign.tutorial.current_step.choices,
      submitted: {}, submitted_count: 0, total_players: 2,
    }
    multiplayer.available_actions = [{
      type: 'party_decision.submit', label: 'Submit', expected_version: 1,
      choice_ids: ['inspect_cold_ash', 'check_wagon_tracks'], submitted: {},
    }]
    mocks.fetch.mockResolvedValueOnce(multiplayer)
    const wrapper = mount(Dnd2024CampaignPanel, {
      props: { gameKey: 'web|campaign|bot', actorId: 'ally', isGm: false },
    })
    await flushPromises()

    expect(wrapper.find('.party-decision-card').exists()).toBe(false)
    expect(wrapper.find('.gm-fallback').exists()).toBe(false)
    expect(wrapper.find('.choice-grid').exists()).toBe(false)
    expect(mocks.submit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('lets the GM resolve an open party decision with an explicit branch', async () => {
    const multiplayer = response('tutorial') as any
    multiplayer.gameplay.campaign.tutorial.requirement_met = true
    multiplayer.gameplay.campaign.tutorial.current_step.choices = [
      { id: 'inspect_cold_ash', label: 'Inspect ash', description: 'Look closer.', next_step_id: 'keepers_plea' },
      { id: 'check_wagon_tracks', label: 'Check tracks', description: 'Search the wagon.', next_step_id: 'keepers_plea' },
    ]
    multiplayer.gameplay.campaign.party_decision = {
      status: 'open', step_id: 'mistbound_road',
      choices: multiplayer.gameplay.campaign.tutorial.current_step.choices,
      submitted: { ally: 'inspect_cold_ash' }, submitted_count: 1, total_players: 2,
    }
    multiplayer.available_actions = [{
      type: 'party_decision.resolve', label: 'Resolve', expected_version: 1,
      choice_ids: ['inspect_cold_ash', 'check_wagon_tracks'],
      submitted: { ally: 'inspect_cold_ash' },
    }]
    mocks.fetch.mockResolvedValueOnce(multiplayer)
    const wrapper = mount(Dnd2024CampaignPanel, {
      props: { gameKey: 'web|campaign|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    const select = wrapper.get('.gm-fallback .party-resolve select')
    await select.setValue('check_wagon_tracks')
    await wrapper.get('.gm-fallback .party-resolve .campaign-primary').trigger('click')
    await flushPromises()

    expect(mocks.submit.mock.calls[0][1]).toMatchObject({
      type: 'party_decision.resolve', choice_id: 'check_wagon_tracks', expected_version: 1,
    })
    wrapper.unmount()
  })
})
