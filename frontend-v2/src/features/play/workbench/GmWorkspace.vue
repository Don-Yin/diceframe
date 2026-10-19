<script setup lang="ts">
import { computed, nextTick, ref, useId } from 'vue'
import { useLocale } from '@/composables/useLocale'
import { workbenchCopy } from './copy'

const props = defineProps<{ round: number; pendingCount?: number; needsAttention?: boolean }>()
const sections = ['todo', 'party', 'scene', 'rules', 'settings'] as const
type Section = typeof sections[number]
const selected = ref<Section>('todo')
const { locale, t } = useLocale()
const copy = computed(() => workbenchCopy(locale.value))
const id = useId()
const pending = computed(() => Math.max(0, Math.trunc(props.pendingCount || 0)))
const tabRefs = new Map<Section, HTMLButtonElement>()
function select(section: Section) { selected.value = section }
defineExpose({ select })
async function navigate(event: KeyboardEvent, section: Section) {
  const index = sections.indexOf(section)
  let target: Section | undefined
  if (event.key === 'ArrowRight') target = sections[(index + 1) % sections.length]
  else if (event.key === 'ArrowLeft') target = sections[(index + sections.length - 1) % sections.length]
  else if (event.key === 'Home') target = sections[0]
  else if (event.key === 'End') target = sections[sections.length - 1]
  if (!target) return
  event.preventDefault()
  selected.value = target
  await nextTick()
  tabRefs.get(target)?.focus()
}
</script>

<template>
  <div class="gm-workspace" data-testid="gm-workspace">
    <header class="gm-console-head gm-workspace-sticky">
      <span aria-hidden="true">GM</span>
      <div><h2>{{ copy.title }}</h2><small>{{ t('roundLabel', { round }) }}</small></div>
    </header>
    <nav class="gm-workspace-tabs gm-workspace-sticky" role="tablist" :aria-label="copy.title">
      <button v-for="section in sections" :id="`${id}-${section}-tab`" :key="section"
        :ref="element => { if (element) tabRefs.set(section, element as HTMLButtonElement) }"
        type="button" role="tab" :aria-selected="selected === section" :aria-controls="`${id}-${section}-panel`"
        :tabindex="selected === section ? 0 : -1" :class="{ active: selected === section }"
        :aria-label="section === 'todo' && needsAttention ? `${copy[section]} · ${copy.attention}` : undefined"
        @click="selected = section" @keydown="navigate($event, section)">
        {{ copy[section] }}
        <span v-if="section === 'todo' && pending" class="gm-task-count">{{ pending }}</span>
        <span v-else-if="section === 'todo' && needsAttention" class="gm-task-count" aria-hidden="true">!</span>
      </button>
    </nav>
    <div class="gm-workspace-body">
      <!-- Keep controllers and unfinished input mounted when changing tools. -->
      <section v-for="section in sections" v-show="selected === section" :id="`${id}-${section}-panel`" :key="section"
        class="gm-workspace-pane" role="tabpanel" :aria-labelledby="`${id}-${section}-tab`" :data-section="section">
        <slot :name="section" />
      </section>
    </div>
  </div>
</template>

<style scoped>
.gm-workspace { display: grid; gap: 10px; min-width: 0; min-height: 0; }
.gm-workspace-body { display: grid; gap: 10px; min-height: 0; overflow: auto; }
.gm-workspace-tabs { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 3px; padding: 4px; border-radius: 10px; background: var(--df-control-bg); border: 1px solid var(--df-border-soft); }
.gm-workspace-tabs button { position: relative; display: flex; flex-wrap: wrap; gap: 3px; min-height: 40px; align-items: center; justify-content: center; padding: 7px 3px; border: 0; background: transparent; font-size: 12px; color: var(--df-text-secondary); }
.gm-workspace-tabs button.active { background: color-mix(in srgb, var(--df-interactive) 15%, var(--df-surface-1)); color: var(--df-interactive-strong); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--df-interactive) 40%, transparent); }
.gm-workspace-tabs button:not(.active):hover { color: var(--df-text); background: var(--df-hover); box-shadow: none; }
.gm-workspace-tabs button:focus-visible { outline: 1px dashed var(--df-text-secondary); outline-offset: 2px; }
.gm-task-count { display: inline-grid; place-items: center; min-width: 16px; min-height: 16px; padding-inline: 3px; border-radius: 9px; background: var(--df-interactive-strong); color: var(--df-control-bg); font-size: 10px; }
.gm-workspace-pane { display: grid; gap: 10px; min-width: 0; }
</style>
