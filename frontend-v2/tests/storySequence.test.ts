import { describe, expect, it } from 'vitest'
import { groupStorySegments, isStorySequence, speakerFallback } from '@/features/play/story/story'
import type { StorySequence } from '@/api/types'

describe('story sequence presentation contract', () => {
  it('accepts only version 1 non-empty typed segments', () => {
    const story: StorySequence = {
      version: 1,
      segments: [
        { id: 'a', kind: 'dialogue', text: 'Hello', speaker_id: 's_0123456789abcdef0123', speaker_name: 'Mara' },
        { id: 'b', kind: 'narration', text: 'The door opens.' },
      ],
    }
    expect(isStorySequence(story)).toBe(true)
    expect(isStorySequence({ version: 2, segments: story.segments })).toBe(false)
    expect(isStorySequence({ version: 1, segments: [{ id: 'x', kind: 'dialogue', text: '' }] })).toBe(false)
    expect(isStorySequence({ version: 1, segments: [{ id: 'x', kind: 'dialogue', text: 'x', speaker_id: 's_0123456789abcdef0123' }] })).toBe(false)
    expect(isStorySequence({ version: 1, segments: [{ id: 'x', kind: 'dialogue', text: 'x', speaker_id: 's_bad', speaker_name: 'Mara' }] })).toBe(false)
  })

  it('groups consecutive same-speaker bubbles without reordering segments', () => {
    const grouped = groupStorySegments({ version: 1, segments: [
      { id: '1', kind: 'dialogue', text: 'one', speaker_id: 's_0123456789abcdef0123' },
      { id: '2', kind: 'dialogue', text: 'two', speaker_id: 's_0123456789abcdef0123' },
      { id: '3', kind: 'narration', text: 'scene' },
    ] })
    expect(grouped.map(item => item.segments.map(segment => segment.id))).toEqual([['1', '2'], ['3']])
    const separated = groupStorySegments({ version: 1, segments: [
      { id: 'a', kind: 'dialogue', text: 'a', speaker_id: 's_0123456789abcdef0123', speaker_name: 'Mara' },
      { id: 'n', kind: 'narration', text: 'n' },
      { id: 'b', kind: 'dialogue', text: 'b', speaker_id: 's_0123456789abcdef0123', speaker_name: 'Mara' },
    ] })
    expect(new Set(separated.map(item => item.key)).size).toBe(3)
  })

  it('uses deterministic initials and color without assigning a stock face', () => {
    expect(speakerFallback('s_0123456789abcdef0123', 'Mara')).toEqual(speakerFallback('s_0123456789abcdef0123', 'Mara'))
    expect(speakerFallback('s_0123456789abcdef0123', 'Mara').initials).toBe('MA')
    expect(speakerFallback('s_0123456789abcdef0123', 'Mara').color).toMatch(/^#[0-9a-f]{6}$/)
  })
})
