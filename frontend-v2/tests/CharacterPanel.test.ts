import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import CharacterPanel from '../src/components/CharacterPanel.vue'

describe('CharacterPanel portrait editing', () => {
  const player = {
    user_id: 'player-1',
    character_name: '艾琳',
    character_sheet: {
      portrait: { kind: 'builtin' as const, id: 'freeform_fantasy:1' },
      hp: 10,
      max_hp: 10,
      attributes: {},
      skills: [],
    },
  }

  it('emits only when the current player may edit the portrait', async () => {
    i18n.global.locale.value = 'zh-CN'
    const editable = mount(CharacterPanel, {
      global: { plugins: [i18n] },
      props: { player, ruleMeta: { rule_id: 'freeform_fantasy' }, portraitEditable: true },
    })
    const editButton = editable.get('button[title]')
    expect(editButton.attributes('title')).toContain('头像')
    await editButton.trigger('click')
    expect(editable.emitted('portrait-click')).toHaveLength(1)

    const readonly = mount(CharacterPanel, {
      global: { plugins: [i18n] },
      props: { player, ruleMeta: { rule_id: 'freeform_fantasy' }, portraitEditable: false },
    })
    expect(readonly.find('button[title]').exists()).toBe(false)
  })
})
