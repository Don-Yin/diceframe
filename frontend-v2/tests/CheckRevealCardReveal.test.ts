import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CheckRevealCard from '../src/components/play/CheckRevealCard.vue'
import { i18n } from '../src/i18n'

describe('CheckRevealCard click-to-reveal presentation', () => {
  beforeEach(() => { i18n.global.locale.value = 'zh-CN' })
  afterEach(() => { vi.useRealTimers() })

  it('masks the result and offers the shared reveal button in click mode', async () => {
    const wrapper = mount(CheckRevealCard, {
      global: { plugins: [i18n] },
      props: {
        check: {
          check_id: 'c6', actor_name: '米拉', label: '攻击检定', dice: 'd20',
          roll: 18, rolls: [18], modifier: 5, total: 23, dc: 15,
          verdict: '成功', is_critical: true,
        },
        clickMode: true,
        reveal: null,
        canReveal: true,
      },
    })
    // 未揭示：机械状态已落盘，但表现层遮罩，不显示结果与详情。
    expect(wrapper.text()).toContain('待揭示')
    expect(wrapper.text()).not.toContain('23')
    expect(wrapper.text()).not.toContain('大成功')
    expect(wrapper.find('details').exists()).toBe(false)
    expect(wrapper.classes()).not.toContain('critical')
    expect(wrapper.classes()).not.toContain('success')
    const button = wrapper.get('button')
    expect(button.text()).toContain('点击揭示骰子')
    await button.trigger('click')
    const emitted = wrapper.emitted('reveal')?.[0]?.[0] as { check_id?: string } | undefined
    expect(emitted?.check_id).toBe('c6')
  })

  it('shows a waiting hint instead of a button for non-revealers', () => {
    const wrapper = mount(CheckRevealCard, {
      global: { plugins: [i18n] },
      props: {
        check: { check_id: 'c7', actor_name: '米拉', label: '检定', dice: 'd20', roll: 9, verdict: '失败' },
        clickMode: true,
        reveal: null,
        canReveal: false,
      },
    })
    expect(wrapper.text()).toContain('等待揭示')
    expect(wrapper.find('.check-reveal-actions button').exists()).toBe(false)
  })

  it('unmasks with a revealed-by caption once the record arrives', async () => {
    const wrapper = mount(CheckRevealCard, {
      global: { plugins: [i18n] },
      props: {
        check: { check_id: 'c8', actor_name: '米拉', label: '检定', dice: 'd20', roll: 9, verdict: '失败' },
        clickMode: true,
        reveal: null,
        canReveal: false,
      },
    })
    expect(wrapper.text()).toContain('待揭示')
    await wrapper.setProps({ reveal: { by: 'gm', at: '2026-09-28T12:00:00Z' }, revealerName: '阿尔登' })
    expect(wrapper.text()).not.toContain('待揭示')
    expect(wrapper.text()).toContain('d20=9')
    expect(wrapper.text()).toContain('由 阿尔登 揭示')
  })

  it('auto mode ignores the reveal state entirely', () => {
    const wrapper = mount(CheckRevealCard, {
      global: { plugins: [i18n] },
      props: {
        check: { check_id: 'c9', actor_name: '米拉', label: '检定', dice: 'd20', roll: 14, total: 14, verdict: '成功' },
      },
    })
    expect(wrapper.text()).toContain('成功')
    expect(wrapper.text()).not.toContain('待揭示')
    expect(wrapper.find('.check-reveal-actions button').exists()).toBe(false)
  })

  it('keeps completed rolls compact and lets the player reopen their dice tray', async () => {
    const wrapper = mount(CheckRevealCard, {
      attachTo: document.body,
      global: { plugins: [i18n] },
      props: { check: { check_id: 'done', dice: 'd20', roll: 14, verdict: '成功' } },
    })
    expect(wrapper.get('[data-testid="dice-tray"]').isVisible()).toBe(false)
    await wrapper.get('[data-testid="dice-tray-toggle"]').trigger('click')
    expect(wrapper.get('[data-testid="dice-tray-toggle"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-testid="dice-tray"]').isVisible(), wrapper.html()).toBe(true)
    expect(wrapper.get('[data-die-value]').attributes('data-die-value')).toBe('14')
    wrapper.unmount()
  })

  it('retains a pending push draft while its dice presentation changes', async () => {
    const check = { check_id: 'push', actor_uid: 'p', dice: 'd100', roll: 80, verdict: '失败',
      push: { schema_version: 1, revision: 1, status: 'pending' as const, run_id: 'r', round: 1, reason: '', consequence: '' } }
    const wrapper = mount(CheckRevealCard, {
      global: { plugins: [i18n] }, props: { check, gameKey: 'g', actorId: 'p' },
    })
    await wrapper.get('textarea').setValue('我再仔细搜查一次')
    expect(wrapper.get('[data-testid="dice-tray"]').isVisible()).toBe(true)
    expect(wrapper.find('[data-testid="dice-tray-toggle"]').exists()).toBe(false)
    await wrapper.setProps({ check: { ...check, rolls: [80] } })
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('我再仔细搜查一次')
    wrapper.unmount()
  })

  it('keeps an unclicked spectator result masked until the shared reveal arrives', async () => {
    vi.useFakeTimers()
    const wrapper = mount(CheckRevealCard, {
      global: { plugins: [i18n] },
      props: {
        check: { check_id: 'c9', actor_name: '米拉', label: '检定', dice: 'd20', roll: 12, total: 17, dc: 15, verdict: '成功' },
        clickMode: true,
        reveal: null,
        canReveal: false,
      },
    })
    expect(wrapper.text()).toContain('等待揭示')
    await vi.advanceTimersByTimeAsync(60000)
    expect(wrapper.text()).not.toContain('17')
    expect(wrapper.text()).not.toContain('秒后自动揭示')
    expect(wrapper.emitted('reveal')).toBeUndefined()
    await wrapper.setProps({ reveal: { by: 'gm', at: '2026-09-30T00:00:00Z' } })
    expect(wrapper.text()).toContain('17')
    expect(wrapper.text()).not.toContain('秒后自动揭示')
    expect(wrapper.emitted('reveal')).toBeUndefined()
  })

  it('shows the shared revealer and keeps the result revealed', async () => {
    vi.useFakeTimers()
    const wrapper = mount(CheckRevealCard, {
      global: { plugins: [i18n] },
      props: {
        check: { check_id: 'c10', actor_name: '米拉', label: '检定', dice: 'd20', roll: 3, verdict: '失败' },
        clickMode: true,
        reveal: null,
        canReveal: true,
        revealerName: '房主',
      },
    })
    await vi.advanceTimersByTimeAsync(3000)
    await wrapper.setProps({ reveal: { by: 'gm', at: '2026-09-30T00:00:00Z' } })
    await vi.advanceTimersByTimeAsync(10000)
    expect(wrapper.text()).toContain('由 房主 揭示')
    expect(wrapper.text()).not.toContain('已自动揭示')
    expect(wrapper.text()).not.toContain('秒后自动揭示')
  })
})
