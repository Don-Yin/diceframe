import { ref, type Ref } from 'vue'
import type { AssistantReactionCategory } from '@/features/assistant/reactions'

export const ASSISTANT_ENABLED_STORAGE_KEY = 'diceframe_assistant_enabled'
export const ASSISTANT_REACTIONS_STORAGE_KEY = 'diceframe_assistant_reactions'
export const ASSISTANT_VOICE_INPUT_STORAGE_KEY = 'diceframe_assistant_voice_input'
export const ASSISTANT_VOICE_REPLY_STORAGE_KEY = 'diceframe_assistant_voice_reply'
export const ASSISTANT_AUTO_NAVIGATE_STORAGE_KEY = 'diceframe_assistant_auto_navigate'
export const ASSISTANT_REACTION_SPEECH_STORAGE_KEY = 'diceframe_assistant_reaction_speech'
export const ASSISTANT_REACTION_CATEGORIES_STORAGE_KEY = 'diceframe_assistant_reaction_categories_off'
const REACTION_CATEGORIES = new Set<string>(['check', 'combat', 'story', 'growth', 'table'])

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Storage is optional; the preference remains effective for this session.
  }
}

function flag(key: string, fallback: boolean): Ref<boolean> {
  const raw = read(key)
  return ref(raw === null ? fallback : raw !== '0')
}

function setFlag(target: Ref<boolean>, key: string, value: boolean): void {
  target.value = value
  write(key, value ? '1' : '0')
}

const enabled = flag(ASSISTANT_ENABLED_STORAGE_KEY, true)
const reactions = flag(ASSISTANT_REACTIONS_STORAGE_KEY, true)
const voiceInput = flag(ASSISTANT_VOICE_INPUT_STORAGE_KEY, true)
const voiceReply = flag(ASSISTANT_VOICE_REPLY_STORAGE_KEY, false)
const reactionSpeech = flag(ASSISTANT_REACTION_SPEECH_STORAGE_KEY, false)
const autoNavigate = flag(ASSISTANT_AUTO_NAVIGATE_STORAGE_KEY, true)
const disabledReactionCategories = ref<AssistantReactionCategory[]>(readDisabledCategories())

function readDisabledCategories(): AssistantReactionCategory[] {
  try {
    const parsed = JSON.parse(read(ASSISTANT_REACTION_CATEGORIES_STORAGE_KEY) || '[]') as unknown
    return Array.isArray(parsed) ? parsed.filter((item): item is AssistantReactionCategory => REACTION_CATEGORIES.has(String(item))) : []
  } catch {
    return []
  }
}

function setEnabled(value: boolean): void { setFlag(enabled, ASSISTANT_ENABLED_STORAGE_KEY, value) }
function toggle(): void { setEnabled(!enabled.value) }
function setReactions(value: boolean): void { setFlag(reactions, ASSISTANT_REACTIONS_STORAGE_KEY, value) }
function setVoiceInput(value: boolean): void { setFlag(voiceInput, ASSISTANT_VOICE_INPUT_STORAGE_KEY, value) }
function setVoiceReply(value: boolean): void { setFlag(voiceReply, ASSISTANT_VOICE_REPLY_STORAGE_KEY, value) }
function setAutoNavigate(value: boolean): void { setFlag(autoNavigate, ASSISTANT_AUTO_NAVIGATE_STORAGE_KEY, value) }
function setReactionSpeech(value: boolean): void { setFlag(reactionSpeech, ASSISTANT_REACTION_SPEECH_STORAGE_KEY, value) }
function setReactionCategory(category: AssistantReactionCategory, on: boolean): void {
  const next = disabledReactionCategories.value.filter(item => item !== category)
  if (!on) next.push(category)
  disabledReactionCategories.value = next
  write(ASSISTANT_REACTION_CATEGORIES_STORAGE_KEY, JSON.stringify(next))
}

export function useAssistantPreferences() {
  return {
    enabled, setEnabled, toggle,
    reactions, setReactions,
    voiceInput, setVoiceInput,
    voiceReply, setVoiceReply,
    reactionSpeech, setReactionSpeech,
    autoNavigate, setAutoNavigate,
    disabledReactionCategories, setReactionCategory,
  }
}
