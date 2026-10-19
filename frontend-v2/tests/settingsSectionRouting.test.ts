import { describe, expect, it } from 'vitest'
import { isSettingsSectionAvailable, legacySettingsFocus, normalizeSettingsSection } from '../src/utils/settingsSections'

// 旧设置入口兼容契约：历史链接里的 #memory 段要落到现在的「模型」页。
describe('normalizeSettingsSection', () => {
  it('keeps the legacy memory alias pointing at models', () => {
    expect(normalizeSettingsSection('memory')).toBe('models')
  })

  it('passes valid section ids through unchanged', () => {
    expect(normalizeSettingsSection('api')).toBe('api')
    expect(normalizeSettingsSection('connection')).toBe('connection')
    expect(normalizeSettingsSection('advanced')).toBe('models')
  })

  it('opens the merged general page for previous voice, Agent and maintenance links', () => {
    for (const section of ['voice', 'agent', 'system']) expect(normalizeSettingsSection(section)).toBe('general')
    expect(legacySettingsFocus('voice')).toBe('tts')
    expect(legacySettingsFocus('agent')).toBe('agent')
    expect(legacySettingsFocus('system')).toBe('logs')
    expect(legacySettingsFocus('toString')).toBeUndefined()
  })

  it('returns null for unknown sections', () => {
    expect(normalizeSettingsSection('missing')).toBeNull()
    expect(normalizeSettingsSection('')).toBeNull()
  })
})

// 独立托管前端才提供 connection 页；内嵌模式下该入口必须隐藏。
describe('isSettingsSectionAvailable', () => {
  it('gates the connection section behind the standalone frontend', () => {
    expect(isSettingsSectionAvailable('connection', true)).toBe(true)
    expect(isSettingsSectionAvailable('connection', false)).toBe(false)
  })

  it('keeps every other section available regardless of host mode', () => {
    expect(isSettingsSectionAvailable('api', false)).toBe(true)
    expect(isSettingsSectionAvailable('about', true)).toBe(true)
  })
})
