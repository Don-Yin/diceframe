<script setup lang="ts">
import { computed } from 'vue'
import { NIcon } from 'naive-ui'
import { VolumeHighOutline } from '@vicons/ionicons5'
import type { LoreKeywords } from '@/utils/renderer'
import type { StorySequence } from '@/api/types'
import PortraitImage from '@/components/PortraitImage.vue'
import { highlightKeywords } from '@/utils/renderer'
import { speakerFallback, groupStorySegments } from './story'
import { ttsSupported, ttsToggle } from '@/utils/tts'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{
  story: StorySequence
  lore?: LoreKeywords
  ruleId?: string
  gameKey?: string
  round?: number
  ttsLanguage?: string
}>()
const { t } = useLocale()
const groups = computed(() => groupStorySegments(props.story))
function speech(text: string, id: string): void {
  ttsToggle(text, `story:${props.round || 0}:${id}`, { lang: props.ttsLanguage, gameKey: props.gameKey, role: 'gm' })
}
function fallback(segment: StorySequence['segments'][number]) {
  return speakerFallback(segment.speaker_id, segment.speaker_name)
}
</script>

<template>
  <section class="story-sequence" data-testid="story-sequence">
    <template v-for="group in groups" :key="group.key">
      <article v-if="group.segments[0]?.kind === 'narration'" class="story-narrator-card">
        <div class="story-narrator-label">{{ t('storyNarrator') }}</div>
        <p v-for="segment in group.segments" :key="segment.id" v-html="highlightKeywords(segment.text, lore)" />
      </article>
      <article v-else class="story-dialogue-group">
        <header class="story-speaker-head">
          <PortraitImage
            v-if="group.segments[0]?.portrait"
            :portrait="group.segments[0]?.portrait"
            :rule-id="ruleId"
            :seed="group.segments[0]?.speaker_id"
            :name="group.segments[0]?.speaker_name"
            :size="38"
          />
          <span v-else class="story-fallback-avatar" :style="{ backgroundColor: fallback(group.segments[0]).color }" aria-hidden="true">{{ fallback(group.segments[0]).initials }}</span>
          <span>{{ group.segments[0]?.speaker_name || t('storyUnknownSpeaker') }}</span>
        </header>
        <p v-for="segment in group.segments" :key="segment.id" class="story-dialogue-bubble" :class="{ 'with-speech': ttsSupported() }">
          <span class="story-dialogue-text" v-html="highlightKeywords(segment.text, lore)" />
          <button v-if="ttsSupported()" type="button" class="story-speech-button" :aria-label="t('ttsSpeakGm')" :title="t('ttsSpeakGm')" @click="speech(segment.text, segment.id)"><NIcon :component="VolumeHighOutline" :size="16" /></button>
        </p>
      </article>
    </template>
  </section>
</template>

<style scoped>
.story-sequence { display: grid; gap: .8rem; min-width: 0; color: var(--df-text); }
.story-narrator-card { padding: .75rem .9rem; border: 1px solid var(--df-border-soft); border-radius: .7rem; background: var(--df-surface-2); color: var(--df-text-secondary); }
.story-narrator-label { font-size: .72rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--df-text-muted); }
.story-narrator-card p, .story-dialogue-bubble { margin: .35rem 0 0; line-height: 1.6; white-space: pre-wrap; }
.story-dialogue-group { max-width: 42rem; min-width: 0; }
.story-speaker-head { display: flex; align-items: center; gap: .45rem; margin: 0 0 .25rem .2rem; font-size: .85rem; font-weight: 700; }
.story-fallback-avatar { display: inline-flex; align-items: center; justify-content: center; width: 38px; height: 38px; border-radius: 999px; color: #fff; font-size: .72rem; }
.story-dialogue-bubble { display: grid; grid-template-columns: minmax(0, 1fr); padding: .7rem .85rem; border: 1px solid var(--df-border-soft); border-radius: .25rem .8rem .8rem .8rem; background: color-mix(in srgb, var(--df-interactive) 9%, var(--df-surface-1)); color: var(--df-text); overflow-wrap: anywhere; }
.story-dialogue-bubble.with-speech { grid-template-columns: minmax(0, 1fr) 32px; gap: 10px; align-items: start; }
.story-dialogue-text { min-width: 0; padding-block: max(0px, calc((32px - 1.6em) / 2)); }
.story-speech-button { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; min-height: 32px; margin: 0; padding: 0; border: 0; background: transparent; color: var(--df-interactive-strong); line-height: 1; cursor: pointer; }
</style>
