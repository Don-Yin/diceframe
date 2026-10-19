import { describe, expect, it } from 'vitest'
import { applyStoryMode } from '@/features/create/createPayload'

describe('creation story mode request', () => {
  it('writes the selected mode into the actual create payload', () => {
    expect(applyStoryMode({ game_name: 'test' }, 'dialogue')).toEqual({ game_name: 'test', story_mode: 'dialogue' })
  })
})
