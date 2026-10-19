<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { CharacterPortrait, LogEntry } from '@/api/types'
import { api } from '@/api/client'
import PortraitImage from '@/components/PortraitImage.vue'
import PortraitPicker from '@/components/admin/PortraitPicker.vue'
import { isStorySequence } from './story'
import { useLocale } from '@/composables/useLocale'
import { useConfirm } from '@/composables/useConfirm'

const props = defineProps<{ gameKey: string; log: LogEntry[]; ruleId?: string }>()
const emit = defineEmits<{ refresh: [] }>()
const { t, locale } = useLocale()
const { confirm } = useConfirm()
type Speaker = { id: string; name: string; portrait?: CharacterPortrait | null; first_round?: number; last_round?: number }
const copy = computed(() => locale.value === 'zh-CN'
  ? { merge: '合并重复人物', target: '合并到', choose: '选择确认为同一人的记录', guest: '临时人物', known: '已登记人物', first: '首次出场', round: '轮', confirm: '确认合并', hint: '仅合并确认为同一人的记录。原始台词保留，统一后续人物编号与头像；优先保留目标头像。' }
  : { merge: 'Merge duplicate speaker', target: 'Merge into', choose: 'Choose the same person', guest: 'Guest speaker', known: 'Registered speaker', first: 'First appearance', round: '', confirm: 'Confirm merge', hint: 'Merge only records of the same person. Original dialogue remains; future identity and portraits are unified, preferring the target portrait.' })
const mergeTargets = ref<Record<string, string>>({})
const search = ref('')
const editing = ref<string | null>(null)
const drafts = ref<Record<string, CharacterPortrait | null>>({})
const saving = ref<string | null>(null)
const error = ref('')
const serverSpeakers = ref<Speaker[]>([])
const loading = ref(false)
const castLoaded = ref(false)
let loadVersion = 0
let saveVersion = 0
let disposed = false
const visibleIds = ref(new Set<string>())
let observer: IntersectionObserver | null = null

function speakersFromLog(): Array<{ id: string; name: string; portrait?: CharacterPortrait | null }> {
  const seen = new Map<string, { id: string; name: string; portrait?: CharacterPortrait | null }>()
  for (const entry of props.log) {
    if (!isStorySequence(entry.story)) continue
    for (const segment of entry.story.segments) {
      if (segment.kind !== 'dialogue' || !segment.speaker_id) continue
      const existing = seen.get(segment.speaker_id)
      if (existing) {
        if (!existing.portrait && segment.portrait) existing.portrait = segment.portrait
        continue
      }
      seen.set(segment.speaker_id, { id: segment.speaker_id, name: segment.speaker_name || segment.speaker_id, portrait: segment.portrait })
    }
  }
  return [...seen.values()]
}
const allSpeakers = computed(() => castLoaded.value ? serverSpeakers.value : speakersFromLog())
const speakers = computed(() => {
  const needle = search.value.trim().toLocaleLowerCase()
  return allSpeakers.value.filter(item => !needle || `${item.name} ${item.id}`.toLocaleLowerCase().includes(needle))
})
function duplicates(item: Speaker) { return item.id.startsWith('g_') ? allSpeakers.value.filter(other => other.id !== item.id && other.name === item.name) : [] }
function identityLabel(item: Speaker) { return `${item.id.startsWith('g_') ? copy.value.guest : copy.value.known}${item.first_round === undefined ? '' : ` · ${copy.value.first} ${item.first_round} ${copy.value.round}`} · ${item.id.slice(-6)}` }
async function merge(item: Speaker) {
  if (saving.value) return
  const target = duplicates(item).find(other => other.id === mergeTargets.value[item.id])
  if (!target) return
  const key = props.gameKey
  const accepted = await confirm({ title: copy.value.merge, content: `${item.name} (${identityLabel(item)}) → ${target.name} (${identityLabel(target)})。${copy.value.hint}`, positiveText: copy.value.confirm, type: 'warning' })
  if (!accepted || key !== props.gameKey || disposed || saving.value) return
  const version = ++saveVersion
  saving.value = item.id; error.value = ''
  try {
    await api(`/games/${encodeURIComponent(key)}/story-speakers/merge`, { method: 'POST', body: JSON.stringify({ source_id: item.id, target_id: target.id }) })
    if (disposed || key !== props.gameKey || version !== saveVersion) return
    drafts.value = {}; editing.value = null; mergeTargets.value = {}
    await loadSpeakers()
    emit('refresh')
  } catch (cause) {
    if (!disposed && key === props.gameKey && version === saveVersion) error.value = cause instanceof Error ? cause.message : String(cause)
  } finally { if (version === saveVersion) saving.value = null }
}

async function loadSpeakers(): Promise<void> {
  const key = props.gameKey
  const version = ++loadVersion
  loading.value = true
  try {
    const result = await api<{ speakers?: Speaker[] }>(`/games/${encodeURIComponent(key)}/story-speakers`)
    if (disposed || version !== loadVersion || key !== props.gameKey) return
    serverSpeakers.value = Array.isArray(result.speakers) ? result.speakers : []
    castLoaded.value = true
    error.value = ''
  } catch (cause: unknown) {
    if (disposed || version !== loadVersion || key !== props.gameKey) return
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    if (version === loadVersion && key === props.gameKey) loading.value = false
  }
}

function observeAvatar(id: string, element: Element | null): void {
  if (!element) return
  if (!observer) {
    visibleIds.value.add(id)
    return
  }
  observer.observe(element)
}
function isVisible(id: string): boolean { return visibleIds.value.has(id) }
function openEditor(item: { id: string; portrait?: CharacterPortrait | null }): void {
  drafts.value = { ...drafts.value, [item.id]: item.portrait || null }
  editing.value = editing.value === item.id ? null : item.id
  error.value = ''
}
function draft(item: { id: string; portrait?: CharacterPortrait | null }): CharacterPortrait | null {
  return drafts.value[item.id] === undefined ? item.portrait || null : drafts.value[item.id]
}
async function save(item: { id: string; portrait?: CharacterPortrait | null }): Promise<void> {
  if (saving.value) return
  const key = props.gameKey
  const version = ++saveVersion
  saving.value = item.id; error.value = ''
  try {
    await api(`/games/${encodeURIComponent(key)}/story-speakers/${encodeURIComponent(item.id)}/portrait`, {
      method: 'PUT', body: JSON.stringify({ portrait: draft(item) }),
    })
    if (disposed || key !== props.gameKey || version !== saveVersion) return
    drafts.value = { ...drafts.value, [item.id]: draft(item) }
    editing.value = null
    await loadSpeakers()
    emit('refresh')
  } catch (cause: unknown) {
    if (disposed || key !== props.gameKey || version !== saveVersion) return
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally { if (version === saveVersion) saving.value = null }
}

onMounted(() => {
  if (typeof IntersectionObserver !== 'undefined') {
    observer = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) {
        const id = (entry.target as HTMLElement).dataset.speakerId
        if (id) visibleIds.value = new Set(visibleIds.value).add(id)
        observer?.unobserve(entry.target)
      }
    }, { rootMargin: '160px' })
  }
  void loadSpeakers()
})
watch(() => props.gameKey, () => {
  saveVersion += 1; saving.value = null; error.value = ''; search.value = ''
  serverSpeakers.value = []; castLoaded.value = false; drafts.value = {}; editing.value = null; mergeTargets.value = {}
  visibleIds.value = new Set(); observer?.disconnect(); void loadSpeakers()
})
watch(() => props.log, () => { void loadSpeakers() }, { deep: true })
onBeforeUnmount(() => { disposed = true; loadVersion += 1; saveVersion += 1; observer?.disconnect(); observer = null })
</script>

<template>
  <section class="story-portraits" data-testid="story-portraits">
    <input v-model="search" type="search" :placeholder="t('storyPortraitSearch')" :aria-label="t('storyPortraitSearch')">
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-if="loading" class="muted">{{ t('storyPortraitsLoading') }}</p>
    <p v-if="!loading && !speakers.length" class="muted">{{ t('storyPortraitsEmpty') }}</p>
    <article v-for="item in speakers" :key="item.id" class="story-portrait-row" :ref="element => observeAvatar(item.id, element as Element | null)" :data-speaker-id="item.id">
      <PortraitImage v-if="isVisible(item.id) || editing === item.id" :portrait="draft(item)" :rule-id="ruleId" :seed="item.id" :name="item.name" :size="42" />
      <span v-else class="story-portrait-placeholder" aria-hidden="true" />
      <div class="story-speaker-name"><strong>{{ item.name }}</strong><small>{{ identityLabel(item) }}</small></div>
      <button type="button" @click="openEditor(item)">{{ t('storyPortraitChange') }}</button>
      <details v-if="duplicates(item).length" class="story-merge-controls">
        <summary>{{ copy.merge }}</summary>
        <label>{{ copy.target }}<select v-model="mergeTargets[item.id]" :disabled="!!saving" data-testid="story-merge-target"><option value="">{{ copy.choose }}</option><option v-for="target in duplicates(item)" :key="target.id" :value="target.id">{{ target.name }} · {{ identityLabel(target) }}</option></select></label>
        <button type="button" :disabled="!mergeTargets[item.id] || !!saving" @click="merge(item)">{{ copy.confirm }}</button>
      </details>
      <div v-if="editing === item.id" class="story-portrait-editor">
        <PortraitPicker v-model="drafts[item.id]" :rule-id="ruleId" :seed="item.id" :name="item.name" />
        <button type="button" class="primary" :disabled="!!saving" @click="save(item)">{{ saving === item.id ? t('saving') : t('storyPortraitSave') }}</button>
      </div>
    </article>
  </section>
</template>

<style scoped>
.story-portraits { display: grid; gap: .65rem; }
.story-portraits > input { width: 100%; }
.story-portrait-row { display: flex; align-items: center; flex-wrap: wrap; gap: .55rem; padding: .5rem; border: 1px solid var(--df-border-soft); border-radius: .55rem; }
.story-speaker-name { flex: 1; display: grid; min-width: 0; gap: 4px; }
.story-speaker-name small { font-size: 11px; color: var(--df-text-muted); overflow-wrap: anywhere; }
.story-merge-controls { flex-basis: 100%; display: block; }
.story-merge-controls summary { cursor: pointer; font-size: 12px; }
.story-merge-controls label { display: grid; gap: 6px; margin: 10px 0; font-size: 12px; }
.story-merge-controls select { width: 100%; min-width: 0; }
.story-portrait-editor { flex-basis: 100%; }
.story-portrait-placeholder { width: 42px; height: 42px; border-radius: 999px; background: var(--df-surface-3); }
</style>
