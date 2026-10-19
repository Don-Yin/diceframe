<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId, type CSSProperties } from 'vue'

defineProps<{ label: string }>()
const panelId = useId()
const open = ref(false)
const root = ref<HTMLElement>()
const trigger = ref<HTMLButtonElement>()
const panel = ref<HTMLElement>()
const panelStyle = ref<CSSProperties>()

function positionPanel() {
  if (!open.value || !trigger.value || !panel.value) return
  const anchor = trigger.value.getBoundingClientRect()
  const viewport = window.visualViewport
  const leftEdge = (viewport?.offsetLeft ?? 0) + 12
  const topEdge = (viewport?.offsetTop ?? 0) + 12
  const rightEdge = leftEdge + (viewport?.width ?? window.innerWidth) - 24
  const bottomEdge = topEdge + (viewport?.height ?? window.innerHeight) - 24
  const width = Math.min(230, rightEdge - leftEdge)
  const below = Math.max(0, bottomEdge - anchor.bottom - 6)
  const above = Math.max(0, anchor.top - topEdge - 6)
  const height = panel.value.scrollHeight + 2
  const downward = height <= below || below >= above
  const available = downward ? below : above
  panelStyle.value = {
    left: `${Math.max(leftEdge, Math.min(anchor.right - width, rightEdge - width))}px`,
    top: `${downward ? Math.max(topEdge, anchor.bottom + 6) : anchor.top - 6 - Math.min(height, available)}px`,
    width: `${width}px`,
    maxHeight: `${available}px`,
  }
}

async function toggle() {
  open.value = !open.value
  if (open.value) {
    await nextTick()
    positionPanel()
    Array.from(panel.value?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], select') ?? [])
      .find(element => getComputedStyle(element).display !== 'none')?.focus({ preventScroll: true })
  }
}
function escape(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !open.value) return
  event.preventDefault()
  event.stopPropagation()
  open.value = false
  trigger.value?.focus()
}
function outside(event: Event) {
  if (event.target instanceof Node && !root.value?.contains(event.target) && !panel.value?.contains(event.target)) open.value = false
}
function selected(event: MouseEvent) {
  if ((event.target as Element).closest('button, a[href]')) open.value = false
}
function scrolled(event: Event) {
  if (!(event.target instanceof Node) || !panel.value?.contains(event.target)) positionPanel()
}
defineExpose({ focusTrigger: () => trigger.value?.focus() })
onMounted(() => {
  document.addEventListener('pointerdown', outside)
  document.addEventListener('scroll', scrolled, true)
  window.addEventListener('resize', positionPanel)
  window.visualViewport?.addEventListener('resize', positionPanel)
  window.visualViewport?.addEventListener('scroll', positionPanel)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', outside)
  document.removeEventListener('scroll', scrolled, true)
  window.removeEventListener('resize', positionPanel)
  window.visualViewport?.removeEventListener('resize', positionPanel)
  window.visualViewport?.removeEventListener('scroll', positionPanel)
})
</script>

<template>
  <div ref="root" class="play-utility-menu" @keydown="escape">
    <button ref="trigger" type="button" data-testid="play-tools-toggle" :aria-expanded="open" :aria-controls="panelId" @click="toggle">
      <span>{{ label }}</span><span aria-hidden="true">⌄</span>
    </button>
    <Teleport to="body">
      <div v-if="open" :id="panelId" ref="panel" class="play-utility-panel" data-testid="play-tools-panel" :style="panelStyle" @keydown="escape" @click="selected">
        <slot />
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.play-utility-menu { position: relative; flex: 0 0 auto; }
.play-utility-menu > button { display: inline-flex; align-items: center; gap: 8px; }
.play-utility-menu > button:hover { transform: none; }
.play-utility-panel { position: fixed; z-index: 79; box-sizing: border-box; display: grid; gap: 4px; width: min(230px, calc(100vw - 24px)); padding: 8px; overflow-y: auto; overscroll-behavior: contain; border: 1px solid var(--df-border-soft); border-radius: 8px; background: var(--df-surface-1); box-shadow: var(--df-shadow); }
.play-utility-panel :deep(button) { display: flex; align-items: center; width: 100%; min-height: 40px; margin: 0; padding: 8px 10px; text-align: start; justify-content: start; white-space: normal; }
@media (max-width: 800px) { .play-utility-menu > button, .play-utility-panel :deep(button) { min-height: 44px; } }
</style>
