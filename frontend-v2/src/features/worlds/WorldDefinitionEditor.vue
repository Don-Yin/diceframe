<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { WorldCloneResponse, WorldCreateResponse, WorldDefinition, WorldDefinitionResponse } from '@/api/types'
import { useLocale, type Locale } from '@/composables/useLocale'
import { CONTENT_LANGUAGE_OPTIONS, contentLanguageOf } from '@/utils/contentLanguage'
import { worldsCopy } from './copy'

export interface WorldDefinitionClonePayload {
  sourceWorldId: string
  worldId: string
  name?: string
  language?: string
}

const props = withDefaults(defineProps<{
  worldId?: string
  mode?: 'view' | 'edit' | 'create'
  source?: 'builtin' | 'user' | 'plugin' | string
  initialName?: string
  initialDescription?: string
  initialLanguage?: string
  showHeading?: boolean
}>(), { worldId: '', mode: 'view', showHeading: true })

const emit = defineEmits<{
  saved: [{ worldId: string; definition: WorldDefinition }]
  cancel: []
  cloned: [WorldDefinitionClonePayload]
}>()

const { locale, t } = useLocale()
const copy = computed(() => worldsCopy(locale.value))
const definition = ref<WorldDefinition | null>(null)
const loading = ref(false)
const loadError = ref('')
const saveError = ref('')
const cloneError = ref('')
const saving = ref(false)
const cloning = ref(false)
const draft = ref({
  name: '',
  description: '',
  language: locale.value as Locale,
  world_setting: '',
  starter_scene: '',
})
let requestEpoch = 0
let operationEpoch = 0

const definitionMatchesWorld = computed(() => Boolean(definition.value && definition.value.world_id === props.worldId))
const creating = computed(() => props.mode === 'create')
const canEdit = computed(() => Boolean(
  (creating.value || (
    props.mode === 'edit'
    && definitionMatchesWorld.value
    && definition.value?.source === 'user'
    && definition.value.editable
  ))
  && !loading.value
  && !loadError.value
  && !saving.value
  && !cloning.value,
))
const readonlyDefinition = computed(() => Boolean(
  !creating.value && (definitionMatchesWorld.value
    ? definition.value?.source !== 'user' || !definition.value.editable
    : props.source && props.source !== 'user'),
))
const canSave = computed(() => Boolean(canEdit.value && draft.value.name.trim() && !saving.value))
const canClone = computed(() => Boolean(readonlyDefinition.value && !cloning.value && !saving.value))
const displayDescription = computed(() => definition.value?.description ?? draft.value.description)

function seedDraft() {
  draft.value = {
    name: props.initialName || props.worldId,
    description: props.initialDescription || '',
    language: contentLanguageOf({ language: props.initialLanguage || locale.value }),
    world_setting: '',
    starter_scene: '',
  }
}

async function loadDefinition() {
  const worldId = props.worldId
  const epoch = ++requestEpoch
  seedDraft()
  definition.value = null
  loadError.value = ''
  saveError.value = ''
  cloneError.value = ''
  if (creating.value) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const result = await api<WorldDefinitionResponse>(
      `/worlds/${encodeURIComponent(worldId)}/definition?language=${encodeURIComponent(locale.value)}`,
    )
    if (epoch !== requestEpoch || props.worldId !== worldId) return
    if (!result.ok || !result.world || result.world.world_id !== worldId) throw new Error(result.error || 'world-definition-missing')
    definition.value = result.world
    draft.value = {
      name: String(result.world.world_name || ''),
      description: String(result.world.description || ''),
      language: contentLanguageOf({ language: result.world.language || locale.value }),
      world_setting: String(result.world.world_setting || ''),
      starter_scene: String(result.world.starter_scene || ''),
    }
  } catch (cause: unknown) {
    if (epoch !== requestEpoch || props.worldId !== worldId) return
    loadError.value = errorMessage(cause)
    definition.value = null
  } finally {
    if (epoch === requestEpoch && props.worldId === worldId) loading.value = false
  }
}

function retry() {
  void loadDefinition()
}

async function save() {
  const worldId = props.worldId
  const wasCreating = creating.value
  if (!canSave.value) return
  const requestAtStart = requestEpoch
  const operationAtStart = ++operationEpoch
  const submitted = { ...draft.value }
  saveError.value = ''
  saving.value = true
  try {
    const result = await api<WorldCreateResponse>(wasCreating ? '/worlds' : `/worlds/${encodeURIComponent(worldId)}`, {
      method: wasCreating ? 'POST' : 'PUT',
      body: JSON.stringify({
        name: submitted.name.trim(),
        description: submitted.description,
        language: submitted.language,
        world_setting: submitted.world_setting,
        starter_scene: submitted.starter_scene,
      }),
    })
    if (!result.ok) throw new Error(result.error || (wasCreating ? 'world-create-failed' : 'world-update-failed'))
    if (requestAtStart !== requestEpoch || operationAtStart !== operationEpoch || props.worldId !== worldId) return
    const savedWorldId = wasCreating ? String(result.world_id || result.id || '') : worldId
    if (!savedWorldId) throw new Error('world-create-missing-id')
    emit('saved', {
      worldId: savedWorldId,
      definition: {
        world_id: savedWorldId,
        world_name: submitted.name.trim(),
        description: submitted.description,
        world_setting: submitted.world_setting,
        starter_scene: submitted.starter_scene,
        language: submitted.language,
        source: 'user',
        editable: true,
      },
    })
  } catch (cause: unknown) {
    if (requestAtStart === requestEpoch && operationAtStart === operationEpoch && props.worldId === worldId) saveError.value = errorMessage(cause)
  } finally {
    if (requestAtStart === requestEpoch && operationAtStart === operationEpoch && props.worldId === worldId) saving.value = false
  }
}

async function cloneToEdit() {
  const sourceWorldId = props.worldId
  if (!canClone.value) return
  const requestAtStart = requestEpoch
  const operationAtStart = ++operationEpoch
  cloneError.value = ''
  cloning.value = true
  try {
    const result = await api<WorldCloneResponse>('/worlds/clone-from-template', {
      method: 'POST',
      body: JSON.stringify({ template_id: sourceWorldId }),
    })
    const worldId = String(result.world_id || '')
    if (!result.ok || !worldId) throw new Error(result.error || 'clone-failed')
    if (requestAtStart !== requestEpoch || operationAtStart !== operationEpoch || props.worldId !== sourceWorldId) return
    emit('cloned', { sourceWorldId, worldId, name: result.name, language: result.language })
  } catch (cause: unknown) {
    if (requestAtStart === requestEpoch && operationAtStart === operationEpoch && props.worldId === sourceWorldId) cloneError.value = errorMessage(cause)
  } finally {
    if (requestAtStart === requestEpoch && operationAtStart === operationEpoch && props.worldId === sourceWorldId) cloning.value = false
  }
}

watch(() => [props.worldId, props.mode], () => {
  operationEpoch += 1
  saving.value = false
  cloning.value = false
  void loadDefinition()
}, { immediate: true })
onBeforeUnmount(() => {
  requestEpoch += 1
  operationEpoch += 1
})
</script>

<template>
  <div class="world-definition-editor" :data-world-id="worldId">
    <p v-if="mode === 'view' && displayDescription" class="muted world-short-intro"><strong>{{ copy.shortIntro }}: </strong>{{ displayDescription }}</p>
    <div v-if="loading" class="notice world-definition-loading">{{ copy.definitionLoading }}</div>
    <div v-else-if="loadError" class="notice world-definition-error">
      <span>{{ copy.definitionLoadFailed }}: {{ loadError }}</span>
      <button type="button" @click="retry">{{ copy.definitionRetry }}</button>
    </div>
    <p v-if="saveError" class="notice world-definition-error">{{ saveError }}</p>
    <p v-if="cloneError" class="notice world-definition-error">{{ cloneError }}</p>

    <div v-if="mode !== 'view'" class="world-metadata-editor">
      <h3 v-if="showHeading">{{ t(creating ? 'newWorld' : 'worldsEditTitle') }}</h3>
      <label><span>{{ t('worldName') }}</span><input v-model="draft.name" :placeholder="t('nameNewWorld')" :readonly="!canEdit"></label>
      <label><span>{{ t('contentLanguage') }}</span><select v-model="draft.language" :disabled="!canEdit"><option v-for="option in CONTENT_LANGUAGE_OPTIONS" :key="option.value" :value="option.value">{{ t(option.labelKey) }}</option></select></label>
      <label><span>{{ copy.shortIntro }}</span><textarea v-model="draft.description" rows="3" :readonly="!canEdit"></textarea></label>
    </div>

    <div v-if="creating || definitionMatchesWorld" class="world-definition-fields">
      <p v-if="readonlyDefinition" class="notice">{{ copy.definitionReadonly }}</p>
      <p class="muted world-defaults-notice">{{ copy.defaultsNotice }}</p>
      <label>
        <span>{{ copy.worldSetting }}</span>
        <textarea v-if="mode !== 'view'" v-model="draft.world_setting" rows="8" maxlength="16000" :readonly="!canEdit" data-testid="world-setting" />
        <textarea v-else :value="definition?.world_setting || ''" rows="8" readonly data-testid="world-setting" />
      </label>
      <label>
        <span>{{ copy.starterScene }}</span>
        <textarea v-if="mode !== 'view'" v-model="draft.starter_scene" rows="6" maxlength="8192" :readonly="!canEdit" data-testid="starter-scene" />
        <textarea v-else :value="definition?.starter_scene || ''" rows="6" readonly data-testid="starter-scene" />
      </label>
    </div>

    <div v-if="mode !== 'view'" class="world-definition-actions">
      <button type="button" @click="emit('cancel')">{{ t('cancel') }}</button>
      <button v-if="readonlyDefinition" type="button" class="world-card-clone" :disabled="!canClone" @click="cloneToEdit">{{ copy.cloneToEdit }}</button>
      <button type="button" class="primary" :disabled="!canSave" @click="save">{{ saving ? t('saving') : t(creating ? 'create' : 'saveAction') }}</button>
    </div>
    <div v-else-if="readonlyDefinition" class="world-definition-actions">
      <button type="button" class="world-card-clone" :disabled="!canClone" @click="cloneToEdit">{{ copy.cloneToEdit }}</button>
    </div>
  </div>
</template>

<style scoped>
.world-definition-editor { display: grid; gap: 12px; }
.world-definition-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 4px; }
</style>
