<script setup lang="ts">
import Modal from '@/components/ui/Modal.vue'
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useLocale } from '@/composables/useLocale'
const props = defineProps<{ inline: boolean; title: string }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useLocale()
const editorRoot = ref<HTMLElement | null>(null)
let opener: HTMLElement | null = null
onMounted(async () => {
  if (!props.inline) return
  opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
  await nextTick()
  editorRoot.value?.querySelector<HTMLInputElement>('input')?.focus()
})
onUnmounted(() => { if (opener?.isConnected) opener.focus() })
</script>

<template>
  <section v-if="inline" ref="editorRoot" class="lore-entry-editor-dialog lore-inline-editor" data-testid="lore-inline-editor" :aria-label="title">
    <header><h2>{{ title }}</h2><button @click="emit('close')">{{ t('cancel') }}</button></header>
    <slot />
    <div class="actions"><slot name="actions" /></div>
  </section>
  <Modal v-else :title="title" dialog-class="lore-entry-editor-dialog" @close="emit('close')">
    <slot />
    <template #actions><slot name="actions" /></template>
  </Modal>
</template>
