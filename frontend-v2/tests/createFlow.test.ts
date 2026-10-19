import { describe, expect, it } from 'vitest'
import { canAdvanceCreateStep, previousCreateStep, type CreateStepState } from '../src/features/create/createFlow'

const state = (overrides: Partial<CreateStepState> = {}): CreateStepState => ({
  step: 1, seed: '', activeRule: '', playMode: 'free', adventureReady: false,
  mode: 'template', customName: '', aiPrompt: '', characterNames: ['冒险者'], ...overrides,
})

describe('create wizard behavior', () => {
  it('requires world and rule selection before leaving the first step', () => {
    expect(canAdvanceCreateStep(state())).toBe(false)
    expect(canAdvanceCreateStep(state({ activeRule: 'coc', mode: 'custom' }))).toBe(false)
    expect(canAdvanceCreateStep(state({ activeRule: 'coc', mode: 'ai' }))).toBe(false)
    expect(canAdvanceCreateStep(state({ activeRule: 'coc', mode: 'custom', customName: '雾港' }))).toBe(true)
    expect(canAdvanceCreateStep(state({ activeRule: 'coc', mode: 'ai', aiPrompt: '海边小镇' }))).toBe(true)
    expect(canAdvanceCreateStep(state({ playMode: 'adventure', activeRule: '', adventureReady: false }))).toBe(false)
    expect(canAdvanceCreateStep(state({ playMode: 'adventure', activeRule: 'dnd', adventureReady: true }))).toBe(true)
  })

  it('keeps the restored settings step free of duplicate content validation', () => {
    expect(canAdvanceCreateStep(state({ step: 2, playMode: 'adventure', activeRule: '', adventureReady: false }))).toBe(true)
    expect(canAdvanceCreateStep(state({ step: 2, playMode: 'adventure', activeRule: 'coc', adventureReady: true }))).toBe(true)
  })

  it('supports going back without changing the collected step state', () => {
    const filled = state({ step: 3, activeRule: 'coc', mode: 'custom', customName: '雾港' })
    expect(previousCreateStep(filled.step)).toBe(2)
    expect(filled.customName).toBe('雾港')
    expect(previousCreateStep(1)).toBe(1)
  })

  it('allows the seed restore path to bypass world and adventure requirements', () => {
    expect(canAdvanceCreateStep(state({ seed: 'restore-123', playMode: 'adventure', activeRule: '' }))).toBe(true)
    expect(canAdvanceCreateStep(state({ step: 2, seed: 'restore-123', activeRule: '' }))).toBe(true)
  })
})
