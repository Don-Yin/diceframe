import type { CharacterSheet, GeneratedRuleResponse, GmStyle, StoryMode } from '@/api/types'
import { onAccessTokenChange } from '@/api/authSession'

export interface CreateDraftSource {
  /** Stable launch identity; display names must not be used here. */
  source: string
  seed?: string
}

export interface CreateDraftSnapshot {
  step: 1 | 2 | 3 | 4
  mode: 'template' | 'custom' | 'ai'
  world: string
  rule: string
  name: string
  description: string
  difficulty: string
  solo: boolean
  openRoom: boolean
  narrativePerspective: 'immersive' | 'third_person'
  narrativePerspectiveTouched: boolean
  storyMode?: StoryMode
  gmStyleFollowWorld: boolean
  gmStyle: GmStyle
  advancementMode: 'milestone' | 'xp'
  advancementAuthority: 'ai_gm' | 'gm'
  gameLanguage: string
  customName: string
  customDesc: string
  aiPrompt: string
  aiRule: string
  aiAutoRule: boolean
  aiGeneratedRule?: GeneratedRuleResponse | null
  loreChoice: string
  selectedBookIds?: string[]
  moduleId: string
  playMode: 'free' | 'adventure' | 'gal'
  adventureChoice: string
  seed: string
  characters: CharacterSheet[]
  cardControl: string[]
  mapBackgroundChoice: string
  sceneImageFile?: File | null
  mapBackgroundFile?: File | null
  /** Keeps a multi-cover default stable while a draft is restored. */
  sceneImageSelectionSeed?: string
}

interface StoredDraft {
  namespace: string
  source: string
  seed: string
  savedAt: number
  snapshot: CreateDraftSnapshot
}

const drafts = new Map<string, StoredDraft>()
let sessionNamespace = 'session:0'
let sessionIdentity = ''
let sessionGeneration = 0

export function setCreateDraftSession(identityToken?: string | null): void {
  const nextIdentity = identityToken || ''
  if (nextIdentity === sessionIdentity) return
  drafts.clear()
  sessionIdentity = nextIdentity
  sessionNamespace = `session:${++sessionGeneration}`
}

function key(source: CreateDraftSource): string {
  return JSON.stringify([sessionNamespace, source.source, source.seed || ''])
}

export function saveCreateDraft(source: CreateDraftSource, snapshot: CreateDraftSnapshot): void {
  // Deliberately omit roomPassword and all credentials from the in-memory snapshot.
  const safeSnapshot = cloneSnapshot(snapshot)
  drafts.set(key(source), { namespace: sessionNamespace, source: source.source, seed: source.seed || '', savedAt: Date.now(), snapshot: safeSnapshot })
}

export function loadCreateDraft(source: CreateDraftSource): CreateDraftSnapshot | null {
  const exact = drafts.get(key(source))
  return exact ? cloneSnapshot(exact.snapshot) : null
}

export function clearCreateDraft(source: CreateDraftSource, seed?: string): void {
  drafts.delete(key({ source: source.source, seed: seed ?? source.seed }))
}

export function clearCreateDraftSession(): void {
  for (const [draftKey, draft] of drafts.entries()) if (draft.namespace === sessionNamespace) drafts.delete(draftKey)
}

export function clearAllCreateDraftsForTests(): void { drafts.clear() }

/** Auth lifecycle hook: login/token rotation must invalidate all in-memory drafts. */
export function clearCreateDraftsOnAuthChange(): void { drafts.clear() }

onAccessTokenChange(clearCreateDraftsOnAuthChange)

function clone<T>(value: T): T { return JSON.parse(JSON.stringify(value)) as T }
function cloneSnapshot(snapshot: CreateDraftSnapshot): CreateDraftSnapshot {
  return {
    ...clone({ ...snapshot, sceneImageFile: undefined, mapBackgroundFile: undefined }),
    sceneImageFile: snapshot.sceneImageFile || null,
    mapBackgroundFile: snapshot.mapBackgroundFile || null,
  }
}
