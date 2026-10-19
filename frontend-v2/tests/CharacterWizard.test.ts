import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import CharacterWizard from '../src/components/admin/CharacterWizard.vue'
import { i18n } from '../src/i18n'

vi.mock('../src/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}))

describe('CharacterWizard equipment damage contract', () => {
  it('keeps a dnd5e damage formula alongside its fixed fallback when submitted', async () => {
    const wrapper = mount(CharacterWizard, {
      global: {
        plugins: [i18n],
        stubs: { PortraitPicker: true, SkillEditor: true, HelpButton: true, GeneratedImageThumbnail: true },
      },
      props: {
        ruleMeta: { rule_id: 'dnd5e', mechanics: 'dnd5e_core' },
        ruleAttrs: [{ key: 'str', name: '力量', min: 3, max: 18 }],
        attrTotal: 60,
      },
    })
    await wrapper.get('input[placeholder]').setValue('骰式角色')
    await wrapper.get('.wizard-actions .primary').trigger('click')
    await wrapper.get('.wizard-actions .primary').trigger('click')
    await wrapper.get('.wizard-actions .primary').trigger('click')
    await wrapper.get('.add-item').trigger('click')
    const row = wrapper.get('.item-row')
    await row.get('.item-name').setValue('长剑')
    await row.get('.item-num').setValue('7')
    await row.get('.item-dice').setValue('1d8')
    await wrapper.get('.wizard-actions .primary').trigger('click')

    const submitted = wrapper.emitted('submit')?.[0]?.[0] as { equipment: Array<Record<string, unknown>> }
    expect(submitted.equipment).toEqual([expect.objectContaining({ damage: 7, damage_dice: '1d8' })])
  })
})
