import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, expect, it } from 'vitest'
import { i18n, LOCALE_STORAGE_KEY, UI_LOCALES } from '../src/i18n'
import { useLocale } from '../src/composables/useLocale'
import LanguagePreferences from '../src/features/admin/settings/LanguagePreferences.vue'

afterEach(() => { i18n.global.locale.value = 'zh-CN'; localStorage.removeItem(LOCALE_STORAGE_KEY) })

it('shares the header language state, persists changes and accepts updates from elsewhere', async () => {
  i18n.global.locale.value = 'zh-CN'
  const Mirror = defineComponent({ setup: useLocale, template: '<output>{{ locale }}</output>' })
  const wrapper = mount(LanguagePreferences, { global: { plugins: [i18n] } })
  const mirror = mount(Mirror, { global: { plugins: [i18n] } })
  expect(wrapper.findAll('option').map(option => option.element.value)).toEqual(UI_LOCALES)
  await wrapper.get('select').setValue('en')
  expect(mirror.text()).toBe('en')
  expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en')
  i18n.global.locale.value = 'zh-CN'
  await wrapper.vm.$nextTick()
  expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('zh-CN')
  wrapper.unmount(); mirror.unmount()
})
