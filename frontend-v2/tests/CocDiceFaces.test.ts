import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import CheckRevealCard from '../src/components/play/CheckRevealCard.vue'

const check = { dice: 'd100', dice_mechanic: 'coc_bonus_penalty', roll: 30, rolls: [100, 30],
  threshold: 60, verdict: '普通成功', advantage_mode: 'advantage',
  percentile_dice: { units: 0, tens: [0, 30], candidates: [100, 30], taken_index: 1, bonus_dice: 1, penalty_dice: 0 } }

beforeEach(() => { i18n.global.locale.value = 'zh-CN' })

describe('CoC authoritative percentile faces', () => {
  it('shows shared units, both tens and the 00 + 0 = 100 combination', () => {
    const wrapper = mount(CheckRevealCard, { props: { check }, global: { plugins: [i18n] } })
    expect(wrapper.get('[data-testid="coc-dice-faces"]').text()).toContain('00 + 0 = 100')
    expect(wrapper.get('[data-testid="coc-dice-faces"]').text()).toContain('30 + 0 = 30')
    expect(wrapper.get('[data-testid="coc-dice-taken"]').text()).toContain('30')
    expect(wrapper.text()).toContain('奖励骰')
    wrapper.unmount()
  })

  it('keeps every percentile face hidden until a shared reveal arrives', () => {
    const wrapper = mount(CheckRevealCard, { props: { check, clickMode: true }, global: { plugins: [i18n] } })
    expect(wrapper.find('[data-testid="coc-dice-faces"]').exists()).toBe(false)
    expect(wrapper.find('.check-math').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('00 + 0')
    wrapper.unmount()
  })

  it('retains generic presentation without a declared percentile projection', () => {
    const wrapper = mount(CheckRevealCard, { props: { check: { dice: 'd100', roll: 42, rolls: [42] } }, global: { plugins: [i18n] } })
    expect(wrapper.find('[data-testid="coc-dice-faces"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
