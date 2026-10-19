import { effectScope, nextTick, ref } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { useAdventureSelection } from '../src/features/create/adventureSelection'

const builtin = { adventure_id: 'shared:quest', source_kind: 'builtin', source_id: '', name: 'Builtin', compatibility: 'compatible' }
const plugin = {
  ...builtin, source_kind: 'plugin', source_id: 'castle', name: 'Castle',
  format: 'diceframe:adventure-graph-v2', world_policy: 'fixed', recommended_world_id: 'castle_world',
  required_runtime: { id: 'core:dnd2024', minimum_version: 1 },
}

function setup(api = vi.fn().mockResolvedValue({ ok: true, adventures: [builtin, plugin] })) {
  const scope = effectScope()
  const rule = ref('legacy'), world = ref('forest'), language = ref('zh-CN'), mode = ref('template'), supported = ref(true)
  const selection = scope.run(() => useAdventureSelection({ rule, world, language, mode, supported, request: api }))!
  return { scope, selection, rule, world, language, supported, api }
}

describe('adventure launch selection', () => {
  it('requests an adventure choice before checking an unselected package for compatibility', async () => {
    const state = setup()
    await flushPromises()
    state.supported.value = false
    state.selection.selectPlayMode('adventure')
    expect(state.selection.issue.value).toBe('adventureSelectionRequired')
    expect(state.selection.ready.value).toBe(false)
    expect(state.selection.bindingPayload.value.adventure_id).toBe('')
    state.scope.stop()
  })
  it('does not restore an old discovery catalogue after the content language changes', async () => {
    let oldResult!: (value: unknown) => void
    let newResult!: (value: unknown) => void
    const oldRequest = new Promise(resolve => { oldResult = resolve })
    const newRequest = new Promise(resolve => { newResult = resolve })
    const api = vi.fn((url: string) => url.endsWith('language=ja') ? newRequest : oldRequest)
    const state = setup(api)
    state.language.value = 'ja'
    await nextTick()
    newResult({ ok: true, adventures: [{ ...builtin, name: 'Japanese discovery' }] })
    await flushPromises()
    oldResult({ ok: true, adventures: [{ ...builtin, name: 'Old discovery' }] })
    await flushPromises()
    expect(state.selection.availableModuleAdventures.value[0]?.name).toBe('Japanese discovery')
    state.scope.stop()
  })

  it('does not apply a pending adventure handoff after the user switches to free play', async () => {
    const state = setup()
    await flushPromises()
    let resolve!: (value: unknown) => void
    state.api.mockReturnValue(new Promise(done => { resolve = done }))
    const launch = state.selection.initializeLaunch({ module_id: 'castle', adventure_id: plugin.adventure_id }, [
      { rule_id: 'dnd', ruleset_runtime: { id: 'core:dnd2024', version: 1, capabilities: { adventure_formats: [plugin.format] } } },
    ] as any, [{ id: 'castle_world' }] as any)
    state.selection.selectPlayMode('free')
    resolve({ ok: true, adventures: [plugin] })
    await launch
    expect(state.selection.playMode.value).toBe('free')
    expect(state.selection.selectedKey.value).toBe('')
    expect(state.world.value).toBe('forest')
    expect(state.rule.value).toBe('legacy')
    state.scope.stop()
  })
  it('uses selected rule/world compatibility rather than global discovery metadata', async () => {
    const api = vi.fn((url: string) => Promise.resolve({ ok: true, adventures: [
      url.includes('rule_id=') ? plugin : { ...plugin, compatibility: 'incompatible', incompatibility_reasons: ['ruleset_runtime_unavailable', 'world_mismatch'] },
    ] }))
    const state = setup(api)
    await state.selection.initializeLaunch({ module_id: 'castle', adventure_id: plugin.adventure_id }, [
      { rule_id: 'dnd', ruleset_runtime: { id: 'core:dnd2024', version: 1, capabilities: { adventure_formats: [plugin.format] } } },
    ] as any, [{ id: 'castle_world' }] as any)
    await flushPromises()
    expect(state.selection.ready.value).toBe(true)
    expect(state.selection.selectedAdventure.value?.compatibility).toBe('compatible')
    expect(api.mock.calls.some(([url]) => url.includes('rule_id=dnd&world_id=castle_world'))).toBe(true)
    state.scope.stop()
  })
  it('discovers the global catalogue before a rule or world is selected', async () => {
    const api = vi.fn().mockResolvedValue({ ok: true, adventures: [builtin] })
    const state = setup(api)
    state.rule.value = ''
    state.world.value = ''
    await flushPromises()
    expect(api.mock.calls.some(([url]) => String(url) === '/adventures?language=zh-CN')).toBe(true)
    expect(state.selection.availableModuleAdventures.value).toHaveLength(1)
    state.scope.stop()
  })

  it('preselects the exact module source, a compatible runtime and its fixed world', async () => {
    const state = setup()
    await state.selection.initializeLaunch({ module_id: 'castle', adventure_id: 'shared:quest' }, [
      { rule_id: 'legacy' },
      { rule_id: 'dnd', ruleset_runtime: { id: 'core:dnd2024', version: 1, capabilities: { adventure_formats: [plugin.format] } } },
    ] as any, [{ id: 'forest' }, { id: 'castle_world' }] as any)
    await flushPromises()
    expect(state.rule.value).toBe('dnd')
    expect(state.world.value).toBe('castle_world')
    expect(state.selection.playMode.value).toBe('adventure')
    expect(state.selection.selectedAdventure.value?.name).toBe('Castle')
    expect(state.selection.bindingPayload.value).toEqual({ adventure_id: 'shared:quest', adventure_source_kind: 'plugin', adventure_source_id: 'castle' })
    expect(state.api.mock.calls.some(([url]) => String(url).includes('rule_id=dnd') && String(url).includes('world_id=castle_world'))).toBe(true)
    state.scope.stop()
  })

  it('keeps an unavailable launch blocked instead of silently creating free play', async () => {
    const state = setup()
    await state.selection.initializeLaunch({ module_id: 'missing', adventure_id: 'shared:quest' }, [] as any, [] as any)
    expect(state.selection.playMode.value).toBe('adventure')
    expect(state.selection.issue.value).toBe('adventureLaunchUnavailable')
    expect(state.selection.ready.value).toBe(false)
    state.selection.selectPlayMode('free')
    expect(state.selection.issue.value).toBe('')
    state.scope.stop()
  })

  it('preserves an incompatible selection after world changes and requires review', async () => {
    const api = vi.fn().mockResolvedValue({ ok: true, adventures: [plugin] })
    const state = setup(api)
    await state.selection.initializeLaunch({ module_id: 'castle', adventure_id: 'shared:quest' }, [
      { rule_id: 'dnd', ruleset_runtime: { id: 'core:dnd2024', version: 1, capabilities: { adventure_formats: [plugin.format] } } },
    ] as any, [{ id: 'castle_world' }] as any)
    api.mockResolvedValue({ ok: true, adventures: [{ ...plugin, compatibility: 'incompatible', incompatibility_reasons: ['world_mismatch'] }] })
    state.world.value = 'forest'
    await flushPromises()
    expect(state.selection.selectedAdventure.value?.adventure_id).toBe('shared:quest')
    expect(state.selection.ready.value).toBe(false)
    expect(state.selection.issue.value).toBe('adventureLaunchIncompatible')
    state.scope.stop()
  })
})
