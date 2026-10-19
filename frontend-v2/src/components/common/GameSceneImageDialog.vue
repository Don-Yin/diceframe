<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { SceneImageRef } from '@/api/types'
import { fileToBase64, resolveGameSceneImageUrl, revokeSceneImageUrl, type SceneImageUploadResponse } from '@/api/sceneImages'
import { ruleSceneUrl } from '@/composables/useBackgroundImages'
import { useLocale } from '@/composables/useLocale'
import { useToast } from '@/composables/useToast'
import AdventureSceneImagePicker from './AdventureSceneImagePicker.vue'
import Modal from '@/components/ui/Modal.vue'

const props = defineProps<{ gameKey: string; ruleId: string; gameName: string }>()
const emit = defineEmits<{ close: []; saved: [gameKey: string, reference: SceneImageRef] }>()
const { t } = useLocale()
const toast = useToast()
const draft = ref<File | null>(null)
const defaultUrl = ref('')
const busy = ref(false)
const error = ref('')
let epoch = 0

watch(() => [props.gameKey, props.ruleId], async () => {
  const requestEpoch = ++epoch
  draft.value = null
  revokeSceneImageUrl(defaultUrl.value)
  defaultUrl.value = ruleSceneUrl(props.ruleId)
  let url: string
  try { url = await resolveGameSceneImageUrl(props.gameKey, props.ruleId, true) }
  catch { return }
  if (requestEpoch !== epoch) { revokeSceneImageUrl(url); return }
  defaultUrl.value = url
}, { immediate: true })

function close() { if (!busy.value) emit('close') }

async function save() {
  if (busy.value || !props.gameKey) return
  const gameKey = props.gameKey
  const requestEpoch = epoch
  const file = draft.value
  busy.value = true
  error.value = ''
  try {
    const payload = file
      ? { file_data: await fileToBase64(file), file_name: file.name }
      : { use_default: true }
    if (requestEpoch !== epoch) return
    const result = await api<SceneImageUploadResponse>(`/games/${encodeURIComponent(gameKey)}/scene-image`, {
      method: 'POST', body: JSON.stringify(payload),
    })
    if (requestEpoch !== epoch) return
    if (!result.ok || !result.scene_image) throw new Error(result.error || t('operationFailed'))
    emit('saved', gameKey, result.scene_image)
    toast.success(t('sceneImageSaved'))
    emit('close')
  } catch (cause: unknown) {
    if (requestEpoch === epoch) error.value = errorMessage(cause)
  } finally {
    if (requestEpoch === epoch) busy.value = false
  }
}

onBeforeUnmount(() => { epoch += 1; revokeSceneImageUrl(defaultUrl.value) })
</script>

<template>
  <Modal :title="t('sceneImageManage')" @close="close">
    <p><strong>{{ gameName }}</strong></p>
    <p class="muted">{{ t('sceneImageGmHint') }}</p>
    <fieldset class="save-cover-picker" :disabled="busy">
      <AdventureSceneImagePicker v-model="draft" :default-url="defaultUrl" />
    </fieldset>
    <p v-if="error" role="alert" class="error-banner">{{ error }}</p>
    <div class="actions">
      <button type="button" :disabled="busy" @click="close">{{ t('cancel') }}</button>
      <button type="button" class="primary" data-testid="save-cover-save" :disabled="busy" @click="save">{{ busy ? t('saving') : t('saveAction') }}</button>
    </div>
  </Modal>
</template>

<style scoped>
.save-cover-picker { border: 0; padding: 0; margin: 0; min-width: 0; }
</style>
