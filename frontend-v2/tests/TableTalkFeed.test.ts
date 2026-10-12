import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import TableTalkFeed from '../src/components/play/TableTalkFeed.vue'

describe('TableTalkFeed', () => {
  it('shows the latest public exchanges and can expand older ones', async () => {
    i18n.global.locale.value = 'zh-CN'
    const exchanges = [1, 2, 3].map(index => ({
      id: `q-${index}`,
      actor_uid: 'p1',
      actor_name: '莱拉',
      question: `问题 ${index}`,
      answer: `公开回答 ${index}`,
      round: index,
      created_at: '',
      visibility: 'party' as const,
    }))
    const wrapper = mount(TableTalkFeed, {
      global: { plugins: [i18n] },
      props: { exchanges },
    })

    expect(wrapper.text()).not.toContain('问题 1')
    expect(wrapper.text()).toContain('公开回答 3')
    await wrapper.get('button').trigger('click')
    expect(wrapper.text()).toContain('问题 1')
  })

  it('can dismiss the feed and shows it again for a new exchange', async () => {
    i18n.global.locale.value = 'zh-CN'
    const first = {
      id: 'q-1',
      actor_uid: 'p1',
      actor_name: '莱拉',
      question: '发生了什么？',
      answer: '你目前只知道这些。',
      round: 1,
      created_at: '',
      visibility: 'party' as const,
    }
    const wrapper = mount(TableTalkFeed, {
      global: { plugins: [i18n] },
      props: { exchanges: [first] },
    })

    await wrapper.get('button[aria-label="关闭"]').trigger('click')
    expect(wrapper.find('.table-talk-feed').exists()).toBe(false)

    await wrapper.setProps({
      exchanges: [first, { ...first, id: 'q-2', question: '又有新问题吗？' }],
    })
    expect(wrapper.find('.table-talk-feed').exists()).toBe(true)
  })
})
