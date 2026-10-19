import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { i18n } from '@/i18n'
import StoryPortraits from '@/features/play/story/StoryPortraits.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('@/api/client', () => ({ api: apiMock }))
vi.mock('@/composables/useConfirm', () => ({ useConfirm: () => ({ confirm: vi.fn().mockResolvedValue(true) }) }))

const speakerId = 's_0123456789abcdef0123'
const log = [{ story: { version: 1 as const, segments: [{ id: '1', kind: 'dialogue' as const, text: 'Hello', speaker_id: speakerId, speaker_name: 'Mara' }] } }]

describe('story portrait management', () => {
  it('loads the complete active speaker list and surfaces PUT errors', async () => {
    apiMock.mockResolvedValueOnce({ speakers: [{ id: speakerId, name: 'Mara', portrait: null }] })
    const wrapper = mount(StoryPortraits, {
      props: { gameKey: 'game', log },
      global: { plugins: [i18n], stubs: { PortraitImage: true, PortraitPicker: true } },
    })
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/games/game/story-speakers')
    expect(wrapper.text()).toContain('Mara')
    await wrapper.get('button').trigger('click')
    apiMock.mockRejectedValueOnce(new Error('portrait denied'))
    await wrapper.get('.story-portrait-editor button.primary').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('portrait denied')
  })

  it('keeps same-named actors separate until the GM selects and confirms a duplicate identity', async () => {
    const guest = 'g_0123456789abcdef0123'
    i18n.global.locale.value = 'zh-CN'
    apiMock.mockResolvedValueOnce({ speakers: [
      { id: guest, name: '报童', first_round: 3 },
      { id: speakerId, name: '报童', first_round: 5 },
    ] })
    const wrapper = mount(StoryPortraits, { props: { gameKey: 'game', log: [] }, global: { plugins: [i18n], stubs: { PortraitImage: true, PortraitPicker: true } } })
    await flushPromises()
    expect(wrapper.findAll('.story-portrait-row')).toHaveLength(2)
    expect(wrapper.get('.story-merge-controls button').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="story-merge-target"]').setValue(speakerId)
    apiMock.mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({ speakers: [{ id: speakerId, name: '报童' }] })
    await wrapper.get('.story-merge-controls button').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/games/game/story-speakers/merge', { method: 'POST', body: JSON.stringify({ source_id: guest, target_id: speakerId }) })
    expect(wrapper.findAll('.story-portrait-row')).toHaveLength(1)
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    wrapper.unmount()
  })
})
