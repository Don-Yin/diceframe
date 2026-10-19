import type { StoryMode } from '@/api/types'

export function normalizeStoryMode(value: unknown): StoryMode {
  return value === 'dialogue' ? 'dialogue' : 'prose'
}
