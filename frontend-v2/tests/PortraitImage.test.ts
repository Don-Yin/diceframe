import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PortraitImage from '../src/components/PortraitImage.vue'

vi.mock('../src/api/avatars', () => ({
  uploadedAvatarUrl: vi.fn(async () => 'blob:mock-avatar'),
}))

afterEach(() => {
  localStorage.clear()
  location.hash = ''
  vi.unstubAllGlobals()
})

describe('PortraitImage', () => {
  it('renders an empty placeholder instead of an auto-assigned portrait when none chosen', () => {
    const wrapper = mount(PortraitImage, {
      props: { name: '爱丽丝', size: 64 },
    })
    expect(wrapper.text()).toBe('爱丽')
    expect(wrapper.html()).not.toContain('avatars/')
  })

  it('renders the builtin image for a valid explicit builtin portrait', () => {
    const wrapper = mount(PortraitImage, {
      props: { name: '鲍勃', size: 64, portrait: { kind: 'builtin', id: 'dnd5e:0' }, ruleId: 'dnd5e' },
    })
    expect(wrapper.html()).toContain('avatars/v3/dnd5e/realistic-1.jpg')
    expect(wrapper.html()).toContain('background-size: cover')
  })

  it('renders an empty placeholder for an invalid builtin id instead of falling back to auto-assignment', () => {
    const wrapper = mount(PortraitImage, {
      props: { name: '卡罗尔', size: 64, portrait: { kind: 'builtin', id: 'dnd5e:999' }, ruleId: 'dnd5e' },
    })
    expect(wrapper.text()).toBe('卡罗')
    expect(wrapper.html()).not.toContain('avatars/')
  })

  it('loads a declared content-pack portrait through the configured backend', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('portrait', {
      status: 200,
      headers: { 'Content-Type': 'image/webp' },
    }))
    const createObjectURL = vi.fn().mockReturnValue('blob:plugin-portrait')
    const revokeObjectURL = vi.fn()
    class MockURL extends URL {}
    MockURL.createObjectURL = createObjectURL
    MockURL.revokeObjectURL = revokeObjectURL
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('URL', MockURL)
    vi.stubGlobal('__DF_STANDALONE__', true)
    localStorage.setItem('trpg_backend_url', 'https://backend.example/diceframe')
    localStorage.setItem(
      `trpg_access_token:${encodeURIComponent('https://backend.example/diceframe')}`,
      'owner-token',
    )

    const wrapper = mount(PortraitImage, {
      props: {
        name: 'Mira',
        size: 64,
        portrait: {
          kind: 'plugin',
          plugin_id: 'portrait pack',
          path: 'assets/portraits/mira one.webp',
        },
      },
    })

    await flushPromises()

    expect(fetchMock.mock.calls[0][0]).toBe(
      'https://backend.example/diceframe/api/plugins/assets/portrait%20pack/assets/portraits/mira%20one.webp',
    )
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer owner-token')
    expect(wrapper.find('img').attributes('src')).toBe('blob:plugin-portrait')
    expect(wrapper.text()).toBe('')
    wrapper.unmount()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:plugin-portrait')
  })
})
