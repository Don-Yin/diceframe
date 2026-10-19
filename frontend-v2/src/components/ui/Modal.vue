<script setup lang="ts">
import { onMounted, onUnmounted, ref, useId } from 'vue'
import { useLocale } from '@/composables/useLocale'

defineProps<{ title: string; dialogClass?: string; closeTestId?: string; closeOnBackdrop?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useLocale()
const titleId = useId()
const dialog = ref<HTMLElement | null>(null)
let opener: HTMLElement | null = null

function onKeydown(event: KeyboardEvent) {
  const openDialogs = document.querySelectorAll('[data-df-dialog]')
  if (event.defaultPrevented || openDialogs[openDialogs.length - 1] !== dialog.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
  } else if (event.key === 'Tab' && dialog.value) {
    const controls = [...dialog.value.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]')]
      .filter(element => element.getClientRects().length > 0)
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (!first) {
      event.preventDefault()
      dialog.value.focus()
    } else if (event.shiftKey && (document.activeElement === first || !dialog.value.contains(document.activeElement))) {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && (document.activeElement === last || !dialog.value.contains(document.activeElement))) {
      event.preventDefault()
      first.focus()
    }
  }
}

onMounted(() => {
  opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
  const initial = dialog.value?.querySelector<HTMLElement>('[autofocus], input:not(:disabled), textarea:not(:disabled), select:not(:disabled)')
  ;(initial || dialog.value)?.focus()
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  if (opener?.isConnected) opener.focus()
})
</script>

<template>
  <Teleport to="body">
    <div class="modal" data-df-ui="modal" @click.self="closeOnBackdrop && emit('close')">
      <section ref="dialog" class="dialog" :class="dialogClass" role="dialog" aria-modal="true" :aria-labelledby="titleId" tabindex="-1" data-df-dialog>
        <header>
          <h2 :id="titleId">{{ title }}</h2>
          <button class="modal-x" type="button" :data-testid="closeTestId" @click="emit('close')" :title="t('close')">✕</button>
        </header>
        <slot />
        <div v-if="$slots.actions" class="actions"><slot name="actions" /></div>
      </section>
    </div>
  </Teleport>
</template>
