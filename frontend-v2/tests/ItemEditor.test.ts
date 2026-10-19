import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ItemEditor from '../src/components/admin/ItemEditor.vue'
import { i18n } from '../src/i18n'

vi.mock('../src/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}))

describe('ItemEditor damage dice contract', () => {
  const equipment = [{ name: '长剑', type: 'weapon', damage: 7, damage_dice: '1d8', slot: 'main_hand' }]

  it('edits damage_dice separately from the fixed damage fallback for dnd5e', async () => {
    const wrapper = mount(ItemEditor, {
      global: { plugins: [i18n], stubs: { HelpButton: true, GeneratedImageThumbnail: true } },
      props: { equipment, inventory: [], damageDiceEnabled: true },
    })

    const dice = wrapper.get('.item-dice')
    expect((dice.element as HTMLInputElement).value).toBe('1d8')
    await dice.setValue('2d6+1')
    expect(equipment[0].damage).toBe(7)
    expect(equipment[0].damage_dice).toBe('2d6+1')
  })

  it('does not expose dice editing for rules without the dnd5e damage capability', () => {
    const wrapper = mount(ItemEditor, {
      global: { plugins: [i18n], stubs: { HelpButton: true, GeneratedImageThumbnail: true } },
      props: { equipment, inventory: [], damageDiceEnabled: false },
    })

    expect(wrapper.find('.item-dice').exists()).toBe(false)
  })
})
