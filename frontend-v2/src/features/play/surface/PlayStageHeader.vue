<script setup lang="ts">
import { computed } from 'vue'
import { useLocale } from '@/composables/useLocale'
import { sceneLabel } from './copy'

const props = withDefaults(defineProps<{
  title: string
  subtitle?: string
  markers?: string[]
  headingTag?: 'h1' | 'h2'
  compactOnMobile?: boolean
  tableLayout?: boolean
}>(), { markers: () => [], headingTag: 'h2' })

const { locale } = useLocale()
const label = computed(() => sceneLabel(locale.value))
const visibleMarkers = computed(() => props.markers.filter(marker => Boolean(marker)))
</script>

<template>
  <header class="scene-strip" :class="{ 'compact-on-mobile': compactOnMobile, 'scene-strip-sticky': tableLayout }">
    <div class="scene-heading" :class="{ 'scene-heading-compact': tableLayout }">
      <span class="scene-label">{{ label }}</span>
      <component :is="headingTag" class="scene-title">{{ title }}</component>
      <p v-if="subtitle" class="scene-subtitle">{{ subtitle }}</p>
      <div v-if="visibleMarkers.length" class="scene-chips">
        <span v-for="marker in visibleMarkers" :key="marker">{{ marker }}</span>
      </div>
    </div>
    <div v-if="$slots.trailing" class="scene-trailing">
      <slot name="trailing" />
    </div>
  </header>
</template>

<style scoped>
.scene-strip { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; min-width: 0; }
.scene-heading { min-width: 0; }
.scene-label { display: block; color: var(--df-text-muted); font-size: .78rem; letter-spacing: .08em; text-transform: uppercase; }
.scene-title { margin: .2rem 0 0; overflow-wrap: anywhere; }
.scene-subtitle { margin: .35rem 0 0; color: var(--df-text-muted); overflow-wrap: anywhere; }
.scene-chips { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .55rem; }
.scene-chips span { border: 1px solid var(--df-border-soft); border-radius: 999px; padding: .2rem .55rem; color: var(--df-text-muted); font-size: .82rem; }
.scene-trailing { flex: 0 0 auto; }
@media (max-width: 640px) { .scene-strip { flex-direction: column; } .scene-trailing { width: 100%; } }
@media (max-width: 800px) {
  .scene-strip.compact-on-mobile { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 8px; min-height: 62px; padding: 8px 10px; }
  .scene-strip.compact-on-mobile .scene-subtitle,
  .scene-strip.compact-on-mobile .scene-chips { display: none; }
  .scene-strip.compact-on-mobile .scene-title { display: block; max-width: none; margin: 2px 0; font-size: 17px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .scene-strip.compact-on-mobile .scene-trailing { width: auto; }
}
</style>
