<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useLocale } from '@/composables/useLocale'
import { searchSettings, settingsSearchCopy, type SettingsSearchResult } from './settingsSearch'

const props = defineProps<{ standaloneFrontend?: boolean }>()
const emit = defineEmits<{ select: [result: SettingsSearchResult] }>()
const { locale } = useLocale()
const copy = computed(() => settingsSearchCopy(locale.value))
const query = ref('')
const active = ref(0)
const open = ref(false)
const results = computed(() => searchSettings(query.value, locale.value, props.standaloneFrontend))
watch(query, () => { active.value = 0; open.value = true })
function choose(result: SettingsSearchResult) { open.value = false; emit('select', result) }
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { query.value = ''; open.value = false }
  if (event.key === 'Enter' && open.value && results.value[active.value]) { event.preventDefault(); choose(results.value[active.value]!) }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault(); open.value = true
    active.value = Math.max(0, Math.min(results.value.length - 1, active.value + (event.key === 'ArrowDown' ? 1 : -1)))
    document.getElementById(`settings-result-${active.value}`)?.scrollIntoView({ block: 'nearest' })
  }
}
function onFocusout(event: FocusEvent) {
  if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node | null)) open.value = false
}
</script>

<template>
  <div class="settings-search" role="search" @focusout="onFocusout">
    <div class="settings-search-field">
      <input v-model="query" type="search" role="combobox" autocomplete="off" data-testid="settings-search" :placeholder="copy.placeholder" :aria-label="copy.placeholder" :aria-expanded="!!query && open" aria-controls="settings-search-results" :aria-activedescendant="open && results.length ? `settings-result-${active}` : undefined" @focus="open = true" @keydown="onKeydown">
      <button v-if="query" type="button" class="settings-search-clear" :aria-label="copy.clear" @click="query = ''">×</button>
    </div>
    <div v-if="query && open" id="settings-search-results" class="settings-search-results" role="listbox" :aria-label="copy.placeholder">
      <p class="settings-search-count" role="status">{{ results.length ? `${results.length} ${copy.results}` : copy.empty }}</p>
      <button v-for="(result, index) in results" :id="`settings-result-${index}`" :key="result.id" type="button" role="option" :aria-selected="active === index" @click="choose(result)">
        <strong>{{ result.label }}</strong><small>{{ result.path.join(' › ') }} · {{ result.description }}</small>
      </button>
    </div>
  </div>
</template>

<style scoped>
.settings-search { margin: 0 0 20px; position: relative; z-index: 12; }
.settings-search-field { display: flex; gap: 8px; }
input { width: 100%; min-width: 0; min-height: 42px; padding: 9px 11px; }
.settings-search-clear { flex: 0 0 42px; }
.settings-search-results { position: absolute; inset: calc(100% + 6px) 0 auto; width: min(420px, calc(100vw - 48px)); max-height: min(440px, 60dvh); overflow-y: auto; padding: 6px; background: var(--df-surface-1); border: 1px solid var(--df-border-soft); border-radius: 10px; box-shadow: 0 12px 30px #0006; }
.settings-search-results button { display: flex; flex-direction: column; align-items: stretch; width: 100%; gap: 4px; padding: 10px 12px; text-align: left; white-space: normal; }
.settings-search-results button[aria-selected="true"] { border-color: var(--df-accent, #72badc); }
.settings-search-results small { opacity: .75; overflow-wrap: anywhere; }
.settings-search-count { margin: 4px 12px 8px; font-size: 12px; opacity: .8; }
:global(.settings-search-highlight) { outline: 2px solid var(--df-accent, #72badc); outline-offset: 4px; border-radius: 6px; scroll-margin-top: calc(var(--section-header-height, 52px) + var(--section-navigation-height, 56px) + 80px); }
</style>
