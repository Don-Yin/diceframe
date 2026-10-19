<script setup lang="ts">
import { useLocale } from '@/composables/useLocale'
import { normalizeLocale, UI_LOCALES, uiLocaleLabel } from '@/i18n'

const { locale, setLocale, t } = useLocale()
function changeLanguage(event: Event) {
  setLocale(normalizeLocale((event.target as HTMLSelectElement).value))
}
</script>

<template>
  <section class="appearance-language-section">
    <label for="settings-system-language">{{ t('systemLanguage') }}</label>
    <select id="settings-system-language" :value="locale" data-testid="settings-system-language" @change="changeLanguage">
      <option v-for="code in UI_LOCALES" :key="code" :value="code">{{ uiLocaleLabel(code) }}</option>
    </select>
    <p class="form-hint">{{ t('systemLanguageHint') }}</p>
  </section>
</template>

<style scoped>
.appearance-language-section { margin-bottom: 20px; }
label { display: block; margin-bottom: 8px; font-weight: 700; }
select { width: min(100%, 320px); }
</style>
