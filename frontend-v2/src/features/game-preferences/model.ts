import type { GamePreferences } from '@/api/types'

export function defaultGamePreferences(): GamePreferences {
  return {
    push_enabled: true, quick_actions_enabled: true, dice_reveal_mode: 'auto', luck_timeout_seconds: 60,
    narrative_perspective: 'auto', story_mode: 'prose', gm_style_override: null,
    advancement_mode: 'milestone', advancement_authority: 'ai_gm',
  }
}

export interface GamePreferenceResponse {
  ok: boolean
  error?: string
  preferences: GamePreferences
  defaults?: GamePreferences
  push_supported: boolean
  can_save_defaults?: boolean
  resume?: { ok?: boolean; advanced?: boolean }
}
