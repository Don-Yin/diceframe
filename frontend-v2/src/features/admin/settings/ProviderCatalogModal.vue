<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NIcon, NModal } from 'naive-ui'
import { RefreshOutline, SearchOutline } from '@vicons/ionicons5'
import { useLocale } from '@/composables/useLocale'
import { modelCapability, type ModelCapability, type ProviderDraft } from '@/utils/providerModels'

type ModelCatalogFilter = 'all' | ModelCapability
type ProviderModelGroup = { name: string; models: string[] }

const props = defineProps<{
  show: boolean
  provider: ProviderDraft | null
  models: string[]
  loading: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  refresh: []
  toggle: [model: string]
  'add-custom': [model: string]
  'add-all': [models: string[]]
}>()

const { t } = useLocale()
const search = ref('')
const filter = ref<ModelCatalogFilter>('all')
const customModel = ref('')

watch(
  () => [props.show, props.provider?.id] as const,
  ([show]) => {
    if (!show) return
    search.value = ''
    filter.value = 'all'
    customModel.value = ''
  },
)

function capability(model: string): ModelCapability {
  return modelCapability(model, props.provider?.model_capabilities[model])
}

const filteredModels = computed(() => {
  const query = search.value.trim().toLowerCase()
  return props.models.filter(model => (
    (!query || model.toLowerCase().includes(query))
    && (filter.value === 'all' || capability(model) === filter.value)
  ))
})

function groupModels(models: string[]): ProviderModelGroup[] {
  const groups = new Map<string, string[]>()
  for (const model of models) {
    const slash = model.indexOf('/')
    const name = slash > 0 ? model.slice(0, slash) : t('providerOtherModels')
    const items = groups.get(name) || []
    items.push(model)
    groups.set(name, items)
  }
  return [...groups.entries()].map(([name, items]) => ({ name, models: items }))
}

const groups = computed(() => groupModels(filteredModels.value))
const filters = computed(() => {
  const definitions: { id: ModelCatalogFilter; label: string }[] = [
    { id: 'all', label: t('modelPickerAll') },
    { id: 'chat', label: t('modelCapabilityChat') },
    { id: 'image', label: t('modelCapabilityImage') },
    { id: 'embedding', label: t('modelCapabilityEmbedding') },
    { id: 'tts', label: t('modelCapabilityTts') },
    { id: 'asr', label: t('modelCapabilityAsr') },
  ]
  return definitions.map(item => ({
    ...item,
    count: item.id === 'all'
      ? props.models.length
      : props.models.filter(model => capability(model) === item.id).length,
  }))
})

function capabilityLabels(model: string): string[] {
  const override = props.provider?.model_capabilities[model]
  const value = capability(model)
  const labels = [override ? t('modelCapabilityManualOverride') : t('modelCapabilityAuto')]
  if (value === 'image') return [...labels, t('modelCapabilityImage')]
  if (value === 'embedding') return [...labels, t('modelCapabilityEmbedding')]
  if (value === 'tts') return [...labels, t('modelCapabilityTts')]
  if (value === 'asr') return [...labels, t('modelCapabilityAsr')]
  labels.push(t('modelCapabilityChat'))
  if (/(reason|thinking|deepseek-r|(^|[-_.])r1|(^|[-_.])o[134])/.test(model.toLowerCase())) {
    labels.push(t('modelCapabilityReasoning'))
  }
  return labels
}

function isSelected(model: string): boolean {
  return Boolean(props.provider?.models.includes(model))
}

function addCustomModel() {
  const model = customModel.value.trim()
  if (!model) return
  emit('add-custom', model)
  customModel.value = ''
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    class="provider-catalog-modal"
    :title="t('providerCatalogTitle', { name: provider?.name || provider?.id || '' })"
    @update:show="emit('update:show', $event)"
  >
    <div class="provider-catalog-tools">
      <label class="provider-catalog-search">
        <NIcon :component="SearchOutline" />
        <input v-model="search" :placeholder="t('modelPickerSearch')">
      </label>
      <NButton :loading="loading" :disabled="!provider" @click="emit('refresh')">
        <template #icon><NIcon :component="RefreshOutline" /></template>
        {{ t('providerRefreshCatalog') }}
      </NButton>
    </div>
    <div class="provider-catalog-filters">
      <button
        v-for="item in filters"
        :key="item.id"
        type="button"
        :class="{ active: filter === item.id }"
        @click="filter = item.id"
      >
        {{ item.label }} <span>{{ item.count }}</span>
      </button>
    </div>
    <div class="provider-catalog-body">
      <section v-for="group in groups" :key="group.name" class="provider-catalog-group">
        <header><strong>{{ group.name }}</strong><span>{{ group.models.length }}</span></header>
        <button
          v-for="modelName in group.models"
          :key="modelName"
          type="button"
          :class="['provider-catalog-row', { selected: isSelected(modelName) }]"
          @click="emit('toggle', modelName)"
        >
          <span class="provider-model-orbit"><i /><i /></span>
          <span class="provider-catalog-copy">
            <strong>{{ modelName }}</strong>
            <small>{{ capabilityLabels(modelName).join(' · ') }}</small>
          </span>
          <span class="provider-catalog-toggle">{{ isSelected(modelName) ? '−' : '+' }}</span>
        </button>
      </section>
      <p v-if="!groups.length" class="provider-model-empty">{{ t('modelPickerEmpty') }}</p>
    </div>
    <footer class="provider-catalog-footer">
      <div class="provider-catalog-custom">
        <input v-model="customModel" :placeholder="t('providerModelPlaceholder')" @keydown.enter.prevent="addCustomModel">
        <button type="button" @click="addCustomModel">{{ t('providerAddModel') }}</button>
      </div>
      <NButton :disabled="!filteredModels.length" @click="emit('add-all', filteredModels)">
        {{ t('providerAddAllModels') }}
      </NButton>
    </footer>
  </NModal>
</template>
