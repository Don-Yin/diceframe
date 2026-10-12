import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import CurrentRoundImageModal from '../src/components/play/CurrentRoundImageModal.vue'
import type { GameDetail, LogEntry, Player } from '../src/api/types'


function mountModal(detail: Partial<GameDetail>, log: LogEntry[], players: Player[] = []) {
  i18n.global.locale.value = 'zh-CN'
  return mount(CurrentRoundImageModal, {
    global: { plugins: [i18n], stubs: { Teleport: true } },
    props: { open: true, gameKey: 'web|room|game', detail: detail as GameDetail, log, players },
  })
}

describe('CurrentRoundImageModal', () => {
  it('drafts the default prompt from scene and narration content only', () => {
    const wrapper = mountModal(
      { scene: '雾港码头', round_number: 5 },
      [{ round: 4, gm_response: 'The party regroups inside the lighthouse.' }],
    )
    const prompt = wrapper.get('textarea').element.value
    expect(prompt).toContain('雾港码头')
    expect(prompt).toContain('The party regroups inside the lighthouse.')
    expect(prompt).not.toContain('第4轮')
  })

  it('keeps style and composition wording out of the client draft', () => {
    const wrapper = mountModal({ scene: '雾港码头', round_number: 5 }, [])
    const prompt = wrapper.get('textarea').element.value
    expect(prompt).toBe('雾港码头')
  })

  it('truncates long narration at the server-side context limit', () => {
    const longNarration = '雾'.repeat(2500)
    const wrapper = mountModal(
      { scene: '雾港码头', round_number: 5 },
      [{ round: 4, gm_response: longNarration }],
    )
    const prompt = wrapper.get('textarea').element.value
    expect(prompt).toBe(`雾港码头\n${'雾'.repeat(1600)}`)
  })

  it('emits the target round and manual payload on generate', async () => {
    const wrapper = mountModal(
      { scene: '雾港码头', round_number: 5 },
      [{ round: 4, gm_response: 'The party regroups inside the lighthouse.' }],
    )
    await wrapper.get('button.primary').trigger('click')
    const payload = wrapper.emitted('generate')?.[0]?.[0] as { prompt: string; round: number; panels: unknown[]; panel_count: number; use_avatar_references: boolean }
    expect(payload.round).toBe(4)
    expect(payload.panels).toEqual([{
      participants: [],
      location: '雾港码头',
      description: 'The party regroups inside the lighthouse.',
    }])
    expect(payload.use_avatar_references).toBe(false)
    expect(payload.panel_count).toBe(1)
    expect(payload.prompt).toContain('The party regroups inside the lighthouse.')
  })

  it('keeps the storyboard control concise', () => {
    const wrapper = mountModal({ scene: '雾港码头', round_number: 5 }, [])
    expect(wrapper.find('select').exists()).toBe(false)
    expect(wrapper.text()).not.toMatch(/分镜格数|按 [1-6] 格分析分镜/)
    expect(wrapper.text()).not.toContain('系统会根据公开叙事判断同时异地或独立关键镜头，自动生成最多六格分镜。')
    expect(wrapper.text()).not.toContain('分镜留空')
  })

  it('enables uploaded portrait references and reports the detected count', async () => {
    const players: Player[] = [
      {
        user_id: 'uploaded-player',
        character_name: '观者',
        character_sheet: { portrait: { kind: 'upload', asset_id: 'avatar-1' } },
      },
      {
        user_id: 'builtin-player',
        character_name: '旅人',
        character_sheet: { portrait: { kind: 'builtin', id: 'freeform_fantasy:0' } },
      },
    ]
    const wrapper = mountModal(
      { scene: '雾港码头', round_number: 5 },
      [{ round: 4, gm_response: 'The party regroups.' }],
      players,
    )
    const checkbox = wrapper.get<HTMLInputElement>('.avatar-reference-toggle input[type="checkbox"]')
    expect(checkbox.attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('已检测到本局 1 个上传头像')

    await checkbox.setValue(true)
    await wrapper.get('button.primary').trigger('click')
    const payload = wrapper.emitted('generate')?.[0]?.[0] as { use_avatar_references: boolean }
    expect(payload.use_avatar_references).toBe(true)
  })

  it('disables portrait references with a specific reason when no upload exists', () => {
    const wrapper = mountModal(
      { scene: '雾港码头', round_number: 5 },
      [],
      [{
        user_id: 'builtin-player',
        character_name: '旅人',
        character_sheet: { portrait: { kind: 'builtin', id: 'freeform_fantasy:0' } },
      }],
    )
    expect(wrapper.get('.avatar-reference-toggle input[type="checkbox"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('本局没有可用的上传头像')
  })

  it('pre-fills multiple panels and submits edited panel content', async () => {
    const wrapper = mountModal(
      { scene: '寄宿屋', round_number: 5 },
      [{ round: 4, gm_response: '门口的老妇人交出簿子；与此同时，塔底的队伍钻入船肋；随后，阿尔比娜回到前厅。' }],
    )
    expect(wrapper.find('select').exists()).toBe(false)
    const locations = wrapper.findAll('input').filter(input => !input.attributes('type'))
    await locations[0].setValue('寄宿屋门链')
    const descriptions = wrapper.findAll('textarea')
    await descriptions[1].setValue('手动确认的塔底关键镜头')
    await wrapper.get('button.primary').trigger('click')
    const payload = wrapper.emitted('generate')?.[0]?.[0] as { panels: Array<{ location: string; description: string }>; panel_count: number }
    expect(payload.panels).toHaveLength(1)
    expect(payload.panel_count).toBe(1)
    expect(payload.panels[0].location).toBe('寄宿屋门链')
    expect(payload.panels[0].description).toBe('手动确认的塔底关键镜头')
  })

  it('lets the player choose up to six panels and blocks incomplete panels', async () => {
    const wrapper = mountModal({ scene: '雾港码头', round_number: 5 }, [])
    expect(wrapper.findAll('.storyboard-panel')).toHaveLength(1)
    await wrapper.findAll('textarea')[1].setValue('')
    await wrapper.get('button.primary').trigger('click')
    expect(wrapper.text()).toContain('请补全每一格的地点和描述。')
    expect(wrapper.emitted('generate')).toBeUndefined()
  })

  it('groups continuous sentences into scene beats and keeps detected characters', () => {
    const players: Player[] = [
      { user_id: 'watcher', character_name: '观者' },
      { user_id: 'emotion', character_name: '情緒' },
      { user_id: 'albina', character_name: '阿尔比娜' },
    ]
    const wrapper = mountModal(
      { scene: '砖墙暗道', round_number: 12 },
      [{ round: 11, gm_response: '观者侧身贴上砖墙。门在他身后合拢。他继续沿甬道前进。站前窄巷里，情緒与阿尔比娜赶到巷口。' }],
      players,
    )

    expect(wrapper.find('select').exists()).toBe(false)
    const panels = wrapper.findAll('.storyboard-panel')
    expect(panels).toHaveLength(1)
  })

})
