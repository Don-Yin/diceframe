<script setup lang="ts">
import { computed } from 'vue'
import { NIcon } from 'naive-ui'
import { AddOutline, SearchOutline } from '@vicons/ionicons5'
import { useLocale } from '@/composables/useLocale'
import type { ProviderDraft } from '@/utils/providerModels'

const props = defineProps<{
  providers: ProviderDraft[]
  activeProviderId: string
  search: string
  readyProviderIds: string[]
  canAdd: boolean
}>()

const emit = defineEmits<{
  'update:activeProviderId': [value: string]
  'update:search': [value: string]
  add: []
}>()

const { t } = useLocale()
const readyIds = computed(() => new Set(props.readyProviderIds))
const filteredProviders = computed(() => {
  const query = props.search.trim().toLowerCase()
  if (!query) return props.providers
  return props.providers.filter(provider => (
    `${provider.name} ${provider.base_url} ${provider.models.join(' ')}`.toLowerCase().includes(query)
  ))
})

function providerMark(provider: ProviderDraft): string {
  return (provider.name || provider.id).trim().slice(0, 1).toUpperCase()
}

function providerStyle(providerId: string) {
  let hash = 0
  for (const character of providerId) hash = ((hash << 5) - hash) + character.charCodeAt(0)
  return { '--provider-hue': String(Math.abs(hash) % 360) }
}
</script>

<template>
  <aside class="provider-library">
    <div class="provider-search-box">
      <NIcon :component="SearchOutline" />
      <input :value="search" :placeholder="t('providerSearch')" @input="emit('update:search', ($event.target as HTMLInputElement).value)">
    </div>
    <div class="provider-list">
      <button
        v-for="provider in filteredProviders"
        :key="provider.id"
        type="button"
        :class="['provider-list-item', { active: activeProviderId === provider.id }]"
        @click="emit('update:activeProviderId', provider.id)"
      >
        <span class="provider-avatar" :style="providerStyle(provider.id)">{{ providerMark(provider) }}</span>
        <span class="provider-list-copy">
          <strong>{{ provider.name || provider.base_url || t('providerNamePlaceholder') }}</strong>
          <small>{{ t('providerCatalogCount', { count: provider.models.length }) }}</small>
        </span>
        <i :class="{ ready: readyIds.has(provider.id) }" />
      </button>
      <p v-if="providers.length && !filteredProviders.length" class="provider-list-empty">
        {{ t('providerSearchEmpty') }}
      </p>
    </div>
    <footer class="provider-library-footer">
      <button type="button" :disabled="!canAdd" @click="emit('add')">
        <NIcon :component="AddOutline" />
        {{ t('providerAdd') }}
      </button>
    </footer>
  </aside>
</template>
