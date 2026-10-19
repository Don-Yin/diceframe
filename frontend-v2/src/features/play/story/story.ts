import type { StorySegment, StorySequence } from '@/api/types'
import { initials } from '@/utils/portraits'

const SPEAKER_ID_RE = /^[sg]_[a-f0-9]{20}$/

export function isStorySequence(value: unknown): value is StorySequence {
  if (!value || typeof value !== 'object') return false
  const candidate = value as { version?: unknown; segments?: unknown }
  if (candidate.version !== 1 || !Array.isArray(candidate.segments) || candidate.segments.length === 0) return false
  return candidate.segments.every(segment => {
    if (!segment || typeof segment !== 'object') return false
    const item = segment as Partial<StorySegment>
    if (!item.id || typeof item.id !== 'string' || !item.text || typeof item.text !== 'string') return false
    if (item.kind !== 'narration' && item.kind !== 'dialogue') return false
    if (item.kind === 'dialogue' && (typeof item.speaker_id !== 'string' || !SPEAKER_ID_RE.test(item.speaker_id)
      || typeof item.speaker_name !== 'string' || !item.speaker_name.trim())) return false
    if (item.speaker_name !== undefined && typeof item.speaker_name !== 'string') return false
    return true
  })
}

export interface StorySegmentGroup { key: string; segments: StorySegment[] }

export function groupStorySegments(story: StorySequence): StorySegmentGroup[] {
  const groups: StorySegmentGroup[] = []
  for (const segment of story.segments) {
    const identity = segment.kind === 'dialogue' ? `dialogue:${segment.speaker_id || 'unknown'}` : `narration:${segment.id}`
    const previous = groups[groups.length - 1]
    if (previous && previous.key.startsWith(`${identity}:`)) previous.segments.push(segment)
    else groups.push({ key: `${identity}:${segment.id}`, segments: [segment] })
  }
  return groups
}

function stableHash(value: string): number {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

export function speakerFallback(speakerId = '', speakerName = ''): { initials: string; color: string } {
  const palette = ['#254b72', '#2f5d50', '#70405f', '#6b4e2e', '#3f4b78', '#4d5f2b', '#704342', '#3f5361']
  return { initials: initials(speakerName), color: palette[stableHash(speakerId) % palette.length] }
}
