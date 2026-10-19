import { afterEach, describe, expect, it } from 'vitest'
import { setAccessToken } from '../src/api/client'
import {
  clearAllCreateDraftsForTests,
  clearCreateDraft,
  clearCreateDraftSession,
  loadCreateDraft,
  saveCreateDraft,
  setCreateDraftSession,
  type CreateDraftSnapshot,
} from '../src/features/create/createDraft'

const snapshot = (overrides: Partial<CreateDraftSnapshot> = {}): CreateDraftSnapshot => ({
  step: 3, mode: 'template', world: 'greymoor', rule: 'dnd2024_srd', name: 'Fog', description: 'Background', difficulty: '标准', solo: true,
  openRoom: false, narrativePerspective: 'immersive', narrativePerspectiveTouched: false, gmStyleFollowWorld: true,
  gmStyle: { tone: '', verbosity: 'normal', pace: 'normal', custom_instructions: '' }, advancementMode: 'milestone', advancementAuthority: 'ai_gm',
  gameLanguage: 'zh-CN', customName: '', customDesc: '', aiPrompt: '', aiRule: 'dnd2024_srd', aiAutoRule: false, loreChoice: '__builtin__', selectedBookIds: [],
  moduleId: '', playMode: 'free', adventureChoice: '', seed: '', characters: [{ character_name: '冒险者', background: '', identity: {}, attributes: {}, skills: [] }],
  cardControl: ['human'], mapBackgroundChoice: 'auto', ...overrides,
})

describe('create draft session', () => {
  afterEach(() => { clearAllCreateDraftsForTests(); setCreateDraftSession(null) })

  it('keeps fields and step by canonical source and seed without retaining a password', () => {
    setCreateDraftSession('token-a')
    const original = snapshot({ seed: 'seed-a' })
    saveCreateDraft({ source: 'adventure:core:story', seed: 'seed-a' }, original)
    original.gmStyle.tone = 'mutated-after-save'
    original.characters[0]!.identity!.origin = 'mutated-after-save'
    expect(loadCreateDraft({ source: 'adventure:core:story', seed: 'seed-a' })).toMatchObject({ step: 3, name: 'Fog', seed: 'seed-a' })
    expect(loadCreateDraft({ source: 'adventure:core:story', seed: 'seed-a' })?.gmStyle.tone).toBe('')
    expect(JSON.stringify(loadCreateDraft({ source: 'adventure:core:story', seed: 'seed-a' }))).not.toContain('password')
    clearCreateDraft({ source: 'adventure:core:story', seed: 'seed-a' })
    expect(loadCreateDraft({ source: 'adventure:core:story', seed: 'seed-a' })).toBeNull()
  })

  it('isolates drafts across launch source, seed, and authenticated session namespace', () => {
    setCreateDraftSession('token-a')
    saveCreateDraft({ source: 'world:greymoor', seed: 'one' }, snapshot({ name: 'One', seed: 'one' }))
    expect(loadCreateDraft({ source: 'world:other', seed: 'one' })).toBeNull()
    expect(loadCreateDraft({ source: 'world:greymoor', seed: 'two' })).toBeNull()
    setCreateDraftSession('token-b')
    expect(loadCreateDraft({ source: 'world:greymoor', seed: 'one' })).toBeNull()
  })

  it('clears the active session drafts through the auth lifecycle hook', () => {
    setCreateDraftSession('token-a')
    saveCreateDraft({ source: 'world:greymoor', seed: '' }, snapshot())
    clearCreateDraftSession()
    expect(loadCreateDraft({ source: 'world:greymoor', seed: '' })).toBeNull()
  })

  it('clears drafts when the API auth lifecycle receives a token, including the same token again', () => {
    setCreateDraftSession('token-a')
    saveCreateDraft({ source: 'world:greymoor', seed: '' }, snapshot())
    setAccessToken('token-a')
    expect(loadCreateDraft({ source: 'world:greymoor', seed: '' })).toBeNull()
    saveCreateDraft({ source: 'world:greymoor', seed: '' }, snapshot())
    setAccessToken('token-a')
    expect(loadCreateDraft({ source: 'world:greymoor', seed: '' })).toBeNull()
  })
})
