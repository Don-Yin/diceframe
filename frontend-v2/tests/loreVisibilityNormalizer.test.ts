import { describe, expect, it } from 'vitest'
import {
  normalizeVisibilityValues,
  sanitizeCharacterVisibility,
  visibilityModeOf,
} from '../src/features/lorebook/visibility'

// 后端 visibility_values 兼容的历史形态，前端编辑端必须同样吃得下。
describe('normalizeVisibilityValues', () => {
  it('normalizes arrays, raw strings, JSON strings, and nullish values', () => {
    expect(normalizeVisibilityValues(['public'])).toEqual(['public'])
    expect(normalizeVisibilityValues('public')).toEqual(['public'])
    expect(normalizeVisibilityValues('Alice,Bob')).toEqual(['Alice', 'Bob'])
    expect(normalizeVisibilityValues('["public"]')).toEqual(['public'])
    expect(normalizeVisibilityValues('["u1","u2"]')).toEqual(['u1', 'u2'])
    expect(normalizeVisibilityValues(null)).toEqual([])
    expect(normalizeVisibilityValues(undefined)).toEqual([])
    expect(normalizeVisibilityValues('')).toEqual([])
  })
})

describe('visibilityModeOf', () => {
  it('classifies historical string shapes identically to arrays', () => {
    expect(visibilityModeOf(['public'])).toBe('public')
    expect(visibilityModeOf('public')).toBe('public')
    expect(visibilityModeOf('*')).toBe('public')
    expect(visibilityModeOf('公开')).toBe('public')
    expect(visibilityModeOf([])).toBe('gm')
    expect(visibilityModeOf(null)).toBe('gm')
    expect(visibilityModeOf(['u1', 'Alice'])).toBe('characters')
  })

  it('matches public markers case-insensitively like the backend', () => {
    expect(visibilityModeOf('PUBLIC')).toBe('public')
    expect(visibilityModeOf('Public')).toBe('public')
    expect(visibilityModeOf('PLAYERS')).toBe('public')
    expect(visibilityModeOf('Players')).toBe('public')
    expect(visibilityModeOf(['PUBLIC'])).toBe('public')
    expect(visibilityModeOf(['All'])).toBe('public')
    expect(visibilityModeOf('公开, Alice')).toBe('public')
  })
})

describe('sanitizeCharacterVisibility', () => {
  it('strips public markers from string and array forms', () => {
    expect(sanitizeCharacterVisibility('*, public, 公开, u1, Alice')).toEqual(['u1', 'Alice'])
    expect(sanitizeCharacterVisibility(['u1', '*', '公开', 'Alice'])).toEqual(['u1', 'Alice'])
    expect(sanitizeCharacterVisibility('*')).toEqual([])
  })

  it('strips case variants of public markers without dropping real names', () => {
    expect(sanitizeCharacterVisibility(['PUBLIC', 'Alice'])).toEqual(['Alice'])
    expect(sanitizeCharacterVisibility(['Public', 'Players', 'Alice'])).toEqual(['Alice'])
  })
})
