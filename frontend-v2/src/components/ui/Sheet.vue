<script setup lang="ts">
import { computed } from 'vue'
import {
  DialogContent,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from 'reka-ui'
import { useLocale } from '@/composables/useLocale'

type SheetSide = 'top' | 'right' | 'bottom' | 'left'

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  side?: SheetSide
  width?: string
  closable?: boolean
}>(), {
  side: 'right',
  width: 'min(440px, 100vw)',
  closable: true,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  close: []
}>()

const { t } = useLocale()
const sheetStyle = computed(() => ({ '--df-sheet-width': props.width }))

function onOpenChange(value: boolean) {
  emit('update:open', value)
  if (!value) emit('close')
}
</script>

<template>
  <DialogRoot :open="open" @update:open="onOpenChange">
    <DialogPortal>
      <div class="df-sheet" data-df-ui="sheet" :data-side="side">
        <DialogOverlay class="df-sheet__overlay" />
        <DialogContent class="df-sheet__content" :style="sheetStyle">
          <header class="df-sheet__header">
            <DialogTitle class="df-sheet__title">{{ title }}</DialogTitle>
            <button
              v-if="closable"
              class="df-sheet__close"
              type="button"
              :title="t('close')"
              @click="emit('update:open', false); emit('close')"
            >
              ✕
            </button>
          </header>
          <div class="df-sheet__body"><slot /></div>
          <footer v-if="$slots.actions" class="df-sheet__actions"><slot name="actions" /></footer>
        </DialogContent>
      </div>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.df-sheet { position: fixed; inset: 0; z-index: 140; pointer-events: none; }
.df-sheet__overlay { position: absolute; inset: 0; pointer-events: auto; background: rgba(0, 0, 0, .72); }
.df-sheet__content {
  position: absolute;
  display: flex;
  flex-direction: column;
  pointer-events: auto;
  overflow: auto;
  max-width: 100vw;
  max-height: 100dvh;
  padding: 18px;
  border: 1px solid var(--df-border);
  background: linear-gradient(180deg, var(--df-surface-1), var(--df-surface-2));
  color: var(--df-text);
  box-shadow: var(--df-shadow), inset 0 1px 0 rgba(255, 255, 255, .05);
}
.df-sheet[data-side='right'] .df-sheet__content,
.df-sheet[data-side='left'] .df-sheet__content { top: 0; bottom: 0; width: var(--df-sheet-width); }
.df-sheet[data-side='right'] .df-sheet__content { right: 0; }
.df-sheet[data-side='left'] .df-sheet__content { left: 0; }
.df-sheet[data-side='top'] .df-sheet__content,
.df-sheet[data-side='bottom'] .df-sheet__content { left: 0; right: 0; width: 100%; }
.df-sheet[data-side='top'] .df-sheet__content { top: 0; }
.df-sheet[data-side='bottom'] .df-sheet__content { bottom: 0; }
.df-sheet__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.df-sheet__title { margin: 0; color: var(--df-text); font-size: 1.1rem; font-weight: 700; }
.df-sheet__body { min-height: 0; flex: 1 1 auto; padding-top: 16px; }
.df-sheet__actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.df-sheet__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  min-width: 28px;
  padding: 0;
  border: 1px solid var(--df-border-soft);
  border-radius: 6px;
  color: var(--df-text-muted);
  background: transparent;
}
.df-sheet__close:hover { color: var(--df-danger-strong); background: rgba(159, 61, 53, .14); }
@media (max-width: 720px) {
  .df-sheet__content { padding: 14px; }
}
</style>
