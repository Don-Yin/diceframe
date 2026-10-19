<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Modal from '@/components/ui/Modal.vue'
import { useLocale } from '@/composables/useLocale'
import { lorebookCopy } from './copy'

export type LorebookCreateScope = 'world' | 'game' | 'global' | 'none'

export interface LorebookCreateDecision {
  name: string
  binding: { scope_kind: 'world' | 'game' | 'global'; scope_id: string } | null
}

const props = defineProps<{
  open: boolean
  worldId: string
  worldName: string
  gameKey?: string
  busy?: boolean
  error?: string
}>()

const emit = defineEmits<{
  close: []
  submit: [decision: LorebookCreateDecision]
}>()

const { locale } = useLocale()
const copy = computed(() => lorebookCopy(locale.value))
const name = ref('')
const scope = ref<LorebookCreateScope>('world')

watch(() => props.open, open => {
  if (!open) return
  name.value = ''
  scope.value = 'world'
})

const canSubmit = computed(() => !props.busy && !!name.value.trim())
const worldScopeLabel = computed(() => `${copy.value.scopeWorld}（${props.worldName || props.worldId}）`)

function submit() {
  if (!canSubmit.value) return
  const binding = scope.value === 'none'
    ? null
    : { scope_kind: scope.value, scope_id: scope.value === 'world' ? props.worldId : scope.value === 'game' ? String(props.gameKey || '') : '' } as LorebookCreateDecision['binding']
  emit('submit', { name: name.value.trim(), binding })
}
</script>

<template>
  <Modal v-if="open" :title="copy.createTitle" dialog-class="lore-book-create-dialog" @close="emit('close')">
    <div class="lore-book-create-form">
      <p v-if="error" class="error-text" role="alert">{{ error }}</p>
      <label>
        <span>{{ copy.createName }}</span>
        <input v-model="name" class="lore-book-create-name" :placeholder="copy.createNamePlaceholder" autofocus>
      </label>
      <label>
        <span>{{ copy.createScope }}</span>
        <select v-model="scope" class="lore-book-create-scope">
          <option value="world">{{ worldScopeLabel }}</option>
          <option value="game" :disabled="!gameKey">{{ copy.scopeGame }}</option>
          <option value="global">{{ copy.scopeGlobal }}</option>
          <option value="none">{{ copy.scopeNone }}</option>
        </select>
      </label>
      <p v-if="scope === 'none'" class="muted">{{ copy.scopeNoneHint }}</p>
    </div>
    <template #actions>
      <button type="button" @click="emit('close')">{{ copy.cancel }}</button>
      <button type="button" class="primary" :disabled="!canSubmit" @click="submit">{{ copy.createSubmit }}</button>
    </template>
  </Modal>
</template>
