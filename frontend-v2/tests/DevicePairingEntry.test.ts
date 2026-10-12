import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({
  networkAddresses: vi.fn(),
  issueCode: vi.fn(),
  listDevices: vi.fn(),
  revokeDevice: vi.fn(),
  revokeAllDevices: vi.fn(),
  loadConfig: vi.fn(),
}))

vi.mock('../src/api/pairing', () => ({
  pairingApi: {
    networkAddresses: mocks.networkAddresses,
    issueCode: mocks.issueCode,
    listDevices: mocks.listDevices,
    revokeDevice: mocks.revokeDevice,
    revokeAllDevices: mocks.revokeAllDevices,
  },
}))
vi.mock('../src/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))
vi.mock('../src/composables/useConfirm', () => ({
  useConfirm: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))
vi.mock('../src/stores/useSettingsStore', () => ({
  useSettingsStore: () => ({
    config: { public_base_url: 'https://gm.example.com' },
    load: mocks.loadConfig,
  }),
}))

import DevicePairingButton from '../src/components/DevicePairingButton.vue'
import DevicePairingModal from '../src/features/admin/settings/DevicePairingModal.vue'

describe('device pairing header entry', () => {
  beforeEach(() => {
    mocks.networkAddresses.mockReset().mockResolvedValue({
      addresses: [{ url: 'http://192.168.1.8:8000' }],
    })
    mocks.issueCode.mockReset().mockResolvedValue({ code: '123456', expires_in: 120 })
    mocks.listDevices.mockReset().mockResolvedValue({
      devices: [
        { id: 'device-1', label: 'Pixel 8', last_seen_at: '2024-05-01T10:00:00Z' },
        { id: 'device-2', label: '', last_seen_at: '' },
      ],
    })
    mocks.revokeDevice.mockReset().mockResolvedValue({ ok: true })
    mocks.revokeAllDevices.mockReset().mockResolvedValue({ ok: true, revoked: 2 })
    mocks.loadConfig.mockReset().mockResolvedValue(undefined)
  })

  it('emits open from the QR button and keeps the shared header button styling', async () => {
    const wrapper = mount(DevicePairingButton, { global: { plugins: [i18n] } })

    const button = wrapper.get('button')
    expect(button.classes()).toContain('theme-toggle')
    expect(button.attributes('title')).toBe(i18n.global.t('pairingTitle'))
    expect(button.attributes('aria-label')).toBe(i18n.global.t('pairingTitle'))
    expect(wrapper.find('.n-icon').exists()).toBe(true)

    await button.trigger('click')
    expect(wrapper.emitted('open')).toHaveLength(1)
    wrapper.unmount()
  })

  it('opens the pairing modal with the shared panel and collapsed paired devices', async () => {
    const wrapper = mount(DevicePairingModal, {
      global: { plugins: [i18n], stubs: { Teleport: true } },
    })
    await flushPromises()

    expect(wrapper.get('.modal .dialog h2').text()).toBe(i18n.global.t('pairingTitle'))
    // 复用现有面板：地址候选、二维码、配对码与设备清单都来自 pairingApi。
    expect(wrapper.find('.pairing-panel').exists()).toBe(true)
    expect(mocks.loadConfig).toHaveBeenCalledOnce()
    expect(mocks.networkAddresses).toHaveBeenCalledOnce()
    expect(mocks.listDevices).toHaveBeenCalledOnce()

    // 已配对设备默认折成一行计数，不铺开整张列表。
    expect(wrapper.find('.pairing-device-list').exists()).toBe(false)
    expect(wrapper.get('.pairing-devices-count').text()).toBe('2')

    await wrapper.get('.pairing-devices-toggle').trigger('click')
    const rows = wrapper.findAll('.pairing-device-row')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('Pixel 8')
    expect(rows[1].text()).toContain(i18n.global.t('pairingUnnamedDevice'))

    await rows[0].get('button').trigger('click')
    await flushPromises()
    expect(mocks.revokeDevice).toHaveBeenCalledWith('device-1')
    wrapper.unmount()
  })

  it('shows the scannable QR code and pairing code inside the modal', async () => {
    // QrCode 是既有共享组件（编码器与 PR A 无关），这里只验证配对面板确实把它
    // 渲染出来了，因此替换成 stub 而不是在 jsdom 里跑真实二维码编码。
    const wrapper = mount(DevicePairingModal, {
      global: { plugins: [i18n], stubs: { Teleport: true, QrCode: true } },
    })
    await flushPromises()

    expect(wrapper.find('qr-code-stub').exists()).toBe(false)
    await wrapper.get('.pairing-generate-btn').trigger('click')
    await flushPromises()

    expect(mocks.issueCode).toHaveBeenCalledOnce()
    expect(wrapper.get('.pairing-code').text()).toBe('123456')
    expect(wrapper.find('qr-code-stub').exists()).toBe(true)
    wrapper.unmount()
  })
})
