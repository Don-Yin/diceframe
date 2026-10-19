<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { WorldCloneResponse } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import Modal from '@/components/ui/Modal.vue'
import { worldsCopy } from './copy'

const props = defineProps<{ worldId: string; worldName: string }>()
const emit = defineEmits<{ close: []; created: [worldId: string] }>()
const { locale, t } = useLocale()
const copy = computed(() => worldsCopy(locale.value))
const busy = ref(false)
const error = ref('')
let epoch = 0

function close() {
  epoch += 1
  emit('close')
}

async function createEditableCopy() {
  if (busy.value) return
  const sourceId = props.worldId
  const operation = ++epoch
  busy.value = true
  error.value = ''
  try {
    const result = await api<WorldCloneResponse>('/worlds/clone-from-template', {
      method: 'POST', body: JSON.stringify({ template_id: sourceId }),
    })
    if (operation !== epoch || props.worldId !== sourceId) return
    const worldId = String(result.world_id || '').trim()
    if (!result.ok || !worldId) throw new Error(result.error || t('operationFailed'))
    emit('created', worldId)
  } catch (cause: unknown) {
    if (operation === epoch && props.worldId === sourceId) error.value = errorMessage(cause)
  } finally {
    if (operation === epoch && props.worldId === sourceId) busy.value = false
  }
}

watch(() => props.worldId, () => { epoch += 1; busy.value = false; error.value = '' })
onBeforeUnmount(() => { epoch += 1 })
</script>

<template>
  <Modal :title="copy.materialsCopyTitle" @close="close">
    <p><strong>{{ worldName }}</strong></p>
    <p>{{ copy.materialsCopyHint }}</p>
    <p v-if="error" class="notice" role="alert">{{ error }}</p>
    <template #actions>
      <button type="button" @click="close">{{ t('cancel') }}</button>
      <button type="button" class="primary" :disabled="busy" @click="createEditableCopy">{{ copy.materialsCopyAction }}</button>
    </template>
  </Modal>
</template>
