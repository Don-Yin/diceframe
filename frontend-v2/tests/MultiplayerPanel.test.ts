import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import MultiplayerPanel from '../src/components/play/MultiplayerPanel.vue'

describe('MultiplayerPanel party rest status', () => {
  it('shows shared readiness and opens the character center for a waiting player', async () => {
    i18n.global.locale.value = 'zh-CN'
    const wrapper = mount(MultiplayerPanel, {
      global: { plugins: [i18n] },
      props: {
        players: [
          { user_id: 'hero-1', character_name: '阿刁' },
          { user_id: 'hero-2', character_name: '调调' },
        ],
        detail: {
          game_key: 'web|room|bot',
          gm_uid: 'hero-1',
          solo_mode: false,
          rest_session: {
            active: true,
            status: 'collecting',
            rest: 'short',
            ready_count: 1,
            active_count: 2,
            participants: [
              { user_id: 'hero-1', character_name: '阿刁', status: 'submitted' },
              { user_id: 'hero-2', character_name: '调调', status: 'waiting' },
            ],
          },
        },
        isGm: false,
        currentUserId: 'hero-2',
      },
    })

    const alert = wrapper.get('[role="status"]')
    expect(alert.text()).toContain('队伍短休')
    expect(alert.text()).toContain('已准备 1/2')
    expect(alert.text()).toContain('阿刁 · 已准备')
    expect(alert.text()).toContain('调调 · 等待')
    expect(alert.get('button').text()).toBe('选择生命骰并准备')

    await alert.get('button').trigger('click')
    expect(wrapper.emitted('open-character-center')).toHaveLength(1)
  })

  it('does not add a rest alert outside an active party rest', () => {
    const wrapper = mount(MultiplayerPanel, {
      global: { plugins: [i18n] },
      props: {
        players: [{ user_id: 'hero-1', character_name: '阿刁' }],
        detail: { game_key: 'web|room|bot', solo_mode: false },
        isGm: false,
        currentUserId: 'hero-1',
      },
    })

    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })
})

describe('MultiplayerPanel AI takeover feedback', () => {
  const players = [
    { user_id: 'hero-1', character_name: '阿刁' },
    { user_id: 'hero-2', character_name: '调调' },
  ]

  function mountWith(hostingUid: string) {
    return mount(MultiplayerPanel, {
      global: { plugins: [i18n] },
      props: {
        players,
        detail: {
          game_key: 'web|room|bot',
          solo_mode: false,
          multiplayer: { submitted_actions: [{ user_id: 'hero-1', text: '我先走' }] },
        },
        isGm: true,
        currentUserId: 'hero-1',
        hostingUid,
      },
    })
  }

  it('shows the takeover hint for the seat being handed to the AI', () => {
    i18n.global.locale.value = 'zh-CN'
    const wrapper = mountWith('hero-2')

    const row = wrapper.findAll('.player-list li')[1]
    expect(row.text()).toContain('AI 正在接管…')
    // 只有被接管的席位显示提示，其它席位保持原有的行动状态。
    expect(wrapper.findAll('.player-list li')[0].text()).toContain('已行动')
  })

  it('shows no takeover hint while nothing is being handed over', () => {
    i18n.global.locale.value = 'zh-CN'
    const wrapper = mountWith('')

    expect(wrapper.text()).not.toContain('AI 正在接管…')
  })
})
