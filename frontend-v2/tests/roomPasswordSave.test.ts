import { describe, expect, it } from 'vitest'

import { buildRoomPasswordSave } from '@/features/play/economyPrompts'

/**
 * The game-settings dialog blanks the room-password field when it opens, so an
 * unconditional save posted an empty password and silently removed the existing
 * one whenever the GM only changed another setting (the review blocker was
 * "changing just the away policy wipes the room password").
 */
describe('room password save gating', () => {
  it('Case A: never posts the password when the GM only changed another setting', () => {
    // 打开弹窗会把输入框清空；没碰过就不该发请求，原有密码必须保持。
    expect(buildRoomPasswordSave(false, '')).toBeNull()
    // 即便输入框里有什么内容，没编辑过也不提交。
    expect(buildRoomPasswordSave(false, 'stale-value')).toBeNull()
  })

  it('Case B: posts exactly what the GM typed once the field was edited', () => {
    expect(buildRoomPasswordSave(true, 'abc123')).toEqual({ password: 'abc123' })
  })

  it('Case C: an edited-but-empty field is an explicit removal', () => {
    // 明确清空 = 明确取消密码保护，仍然必须发请求。
    expect(buildRoomPasswordSave(true, '')).toEqual({ password: '' })
  })
})
