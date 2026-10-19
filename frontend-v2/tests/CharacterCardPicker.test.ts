import { DOMWrapper, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import CharacterCardPicker from '../src/components/admin/CharacterCardPicker.vue'
import { i18n } from '../src/i18n'

const cards = [
  { card_id: 'same-rule', character_name: '同名角色', rule_id: 'freeform_fantasy', race: '人类', class: '战士' },
  { card_id: 'other-rule', character_name: '同名角色', rule_id: 'freeform_coc', race: '人类', class: '侦探' },
]

afterEach(() => { document.body.innerHTML = '' })

describe('CharacterCardPicker', () => {
  it('keeps same-name cards distinct and emits the selected original card with its conversion warning', async () => {
    const wrapper = mount(CharacterCardPicker, {
      attachTo: document.body,
      props: { cards, targetRuleId: 'freeform_fantasy' },
      global: { plugins: [i18n], stubs: { PortraitImage: true } },
    })
    const choices = new DOMWrapper(document.body).findAll('.card-choice')
    expect(choices).toHaveLength(2)
    expect(choices[0].find('small').exists()).toBe(false)
    expect(choices[1].find('small').exists()).toBe(true)
    await choices[1].trigger('click')
    expect(wrapper.emitted('pick')).toEqual([[cards[1]]])
    expect(wrapper.emitted('close')).toBeUndefined()
    wrapper.unmount()
  })

  it('keeps the empty library and its close controls usable', async () => {
    const wrapper = mount(CharacterCardPicker, {
      attachTo: document.body, props: { cards: [] }, global: { plugins: [i18n] },
    })
    const body = new DOMWrapper(document.body)
    expect(body.get('[role="dialog"]').text()).toContain(i18n.global.t('characterLibraryEmpty'))
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(wrapper.emitted('close')).toHaveLength(1)
    await body.get('.modal').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(2)
    wrapper.unmount()
  })
})
