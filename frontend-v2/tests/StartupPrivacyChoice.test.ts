import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import StartupPrivacyChoice from '../src/components/common/StartupPrivacyChoice.vue'

const mocks = vi.hoisted(() => ({
  hubPreferences: vi.fn(),
  updateHubPreferences: vi.fn(),
}))

const legalDocuments = {
  terms: { version: '1.0', updated_at: '2026-08-11', language: 'zh', sha256: 'a'.repeat(64) },
  privacy: { version: '1.0', updated_at: '2026-08-11', language: 'zh', sha256: 'b'.repeat(64) },
} as const

vi.mock('../src/api/plugins', () => ({
  pluginApi: {
    hubPreferences: mocks.hubPreferences,
    updateHubPreferences: mocks.updateHubPreferences,
  },
}))

vi.mock('../src/api/client', () => ({
  errorMessage: (error: unknown) => error instanceof Error ? error.message : String(error || ''),
}))

vi.mock('../src/composables/useLocale', () => ({
  useLocale: () => ({ locale: { value: 'zh-CN' }, t: (key: string) => key }),
}))

function mountChoice() {
  return mount(StartupPrivacyChoice, {
    global: {
      stubs: {
        teleport: true,
      },
    },
  })
}

describe('StartupPrivacyChoice', () => {
  beforeEach(() => {
    mocks.hubPreferences.mockReset()
    mocks.updateHubPreferences.mockReset()
    mocks.updateHubPreferences.mockResolvedValue({
      available: true,
      telemetry_enabled: true,
      choice_made: true,
      identity_created: false,
      legal_version: '1.0',
      legal_accepted: true,
      legal_documents: legalDocuments,
    })
  })

  it('settles immediately when a choice was already recorded', async () => {
    mocks.hubPreferences.mockResolvedValue({
      available: true,
      telemetry_enabled: false,
      choice_made: true,
      identity_created: false,
      legal_version: '1.0',
      legal_accepted: true,
      legal_documents: legalDocuments,
    })
    const wrapper = mountChoice()
    await flushPromises()

    expect(wrapper.emitted('settled')).toHaveLength(1)
    expect(mocks.updateHubPreferences).not.toHaveBeenCalled()
  })

  it('requires legal acceptance while keeping anonymous statistics off by default', async () => {
    mocks.hubPreferences.mockResolvedValue({
      available: true,
      telemetry_enabled: false,
      choice_made: false,
      identity_created: false,
      legal_version: '1.0',
      legal_accepted: false,
      legal_documents: legalDocuments,
    })
    const wrapper = mountChoice()
    await flushPromises()

    expect(wrapper.get('[role="switch"]').attributes('aria-checked')).toBe('false')
    expect(wrapper.get('[data-testid="startup-privacy-continue"]').attributes('disabled')).toBeDefined()
    expect(mocks.updateHubPreferences).not.toHaveBeenCalled()

    await wrapper.get('[role="checkbox"]').trigger('click')
    await wrapper.get('[data-testid="startup-privacy-continue"]').trigger('click')
    await flushPromises()

    expect(mocks.updateHubPreferences).toHaveBeenCalledWith(false, legalDocuments, 'zh-CN')
    expect(wrapper.emitted('settled')).toHaveLength(1)
  })

  it('allows actively opting in before continuing', async () => {
    mocks.hubPreferences.mockResolvedValue({
      available: true,
      telemetry_enabled: true,
      choice_made: false,
      identity_created: false,
      legal_version: '1.0',
      legal_accepted: false,
      legal_documents: legalDocuments,
    })
    const wrapper = mountChoice()
    await flushPromises()

    await wrapper.get('[role="checkbox"]').trigger('click')
    await wrapper.get('[role="switch"]').trigger('click')
    await wrapper.get('[data-testid="startup-privacy-continue"]').trigger('click')
    await flushPromises()

    expect(mocks.updateHubPreferences).toHaveBeenCalledWith(true, legalDocuments, 'zh-CN')
    expect(wrapper.emitted('settled')).toHaveLength(1)
  })

  it('preserves an existing telemetry opt-in when legal dates require confirmation again', async () => {
    mocks.hubPreferences.mockResolvedValue({
      available: true,
      telemetry_enabled: true,
      choice_made: true,
      identity_created: true,
      legal_version: 'terms:2026-08-11|privacy:2026-08-11',
      legal_accepted: false,
      legal_documents: legalDocuments,
    })
    const wrapper = mountChoice()
    await flushPromises()

    expect(wrapper.get('[role="switch"]').attributes('aria-checked')).toBe('true')
    await wrapper.get('[role="checkbox"]').trigger('click')
    await wrapper.get('[data-testid="startup-privacy-continue"]').trigger('click')
    await flushPromises()

    expect(mocks.updateHubPreferences).toHaveBeenCalledWith(true, legalDocuments, 'zh-CN')
  })
})
