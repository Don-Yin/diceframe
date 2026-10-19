<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { LorebookUsageBook, LorebookUsageResponse } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import { usageCopy } from './usageCopy'

const props = withDefaults(defineProps<{
  gameKey: string
  viewer?: string
  refreshToken?: number
}>(), { viewer: 'gm', refreshToken: 0 })

const { locale } = useLocale()
const copy = computed(() => usageCopy(locale.value))
const library = ref<LorebookUsageResponse['library'] | null>(null)
const game = ref<LorebookUsageResponse['game'] | null>(null)
const loading = ref(false)
const error = ref('')
let requestEpoch = 0

const identity = () => `${props.gameKey}|${props.viewer}|${props.refreshToken}`
function format(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? ''))
}

async function load() {
  const epoch = ++requestEpoch
  const requestIdentity = identity()
  loading.value = true
  error.value = ''
  library.value = null
  game.value = null
  try {
    const query = new URLSearchParams({ viewer: props.viewer || 'gm' })
    if (props.gameKey) query.set('game_key', props.gameKey)
    const result = await api<LorebookUsageResponse>(`/lorebooks/usage?${query.toString()}`)
    if (epoch !== requestEpoch || requestIdentity !== identity()) return
    if (!result.ok) throw new Error(result.error || 'lorebook-usage-failed')
    library.value = result.library
    game.value = result.game
  } catch (cause: unknown) {
    if (epoch !== requestEpoch || requestIdentity !== identity()) return
    library.value = null
    game.value = null
    error.value = errorMessage(cause)
  } finally {
    if (epoch === requestEpoch && requestIdentity === identity()) loading.value = false
  }
}

function retry() { void load() }
function scopeLabel(scope: string): string {
  const labels: Record<string, string> = {
    world: copy.value.scopeWorld, game: copy.value.scopeGame,
    global: copy.value.scopeGlobal, character: copy.value.scopeCharacter,
  }
  return labels[scope] || copy.value.scopeUnbound
}
function bookState(book: LorebookUsageBook): string { return book.enabled ? copy.value.enabled : copy.value.disabled }

watch(() => [props.gameKey, props.viewer, props.refreshToken], load, { immediate: true })
onBeforeUnmount(() => { requestEpoch += 1 })
</script>

<template>
  <section class="lorebook-usage-summary" data-testid="lorebook-usage" aria-live="polite">
    <div v-if="loading" class="lorebook-usage-state notice">{{ copy.loading }}</div>
    <div v-else-if="error" class="lorebook-usage-state notice">
      <span>{{ copy.loadFailed }}: {{ error }}</span>
      <button type="button" data-testid="lorebook-usage-retry" @click="retry">{{ copy.retry }}</button>
    </div>
    <template v-else-if="library && game">
      <article class="lorebook-usage-card">
        <h3>{{ format(copy.librarySummary, { enabled: library.enabled, total: library.total }) }}</h3>
        <p class="muted">{{ copy.libraryHint }}</p>
        <details data-testid="lorebook-usage-library">
          <summary>{{ copy.showBooks }}</summary>
          <p v-if="!library.books.length" class="muted">{{ copy.noBooks }}</p>
          <ul v-else>
            <li v-for="book in library.books" :key="book.id">
              <strong>{{ book.name }}</strong>
              <span>{{ bookState(book) }} · {{ copy.scope }}: {{ scopeLabel(book.scope) }} · {{ copy.entries }}: {{ book.entry_count }}</span>
            </li>
          </ul>
        </details>
      </article>
      <article class="lorebook-usage-card">
        <h3 v-if="game.status === 'ready' && game.count !== null">{{ format(copy.gameSummary, { count: game.count }) }}</h3>
        <h3 v-else-if="game.status === 'none'">{{ copy.noneGame }}</h3>
        <h3 v-else>{{ copy.unavailableGame }}</h3>
        <p class="muted">{{ game.status === 'ready' ? `${game.world_name} · ${copy.gameHint}` : copy.gameHint }}</p>
        <details v-if="game.status === 'ready'" data-testid="lorebook-usage-game">
          <summary>{{ copy.showBooks }}</summary>
          <p v-if="!game.books.length" class="muted">{{ copy.noBooks }}</p>
          <ul v-else>
            <li v-for="book in game.books" :key="book.id">
              <strong>{{ book.name }}</strong>
              <span>{{ bookState(book) }} · {{ copy.scope }}: {{ scopeLabel(book.scope) }} · {{ copy.entries }}: {{ book.entry_count }}</span>
            </li>
          </ul>
        </details>
      </article>
    </template>
  </section>
</template>

<style scoped>
.lorebook-usage-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 12px 0; }
.lorebook-usage-card { min-width: 0; padding: 12px; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-md); background: var(--df-surface-2); }
.lorebook-usage-card h3 { margin: 0; color: var(--df-text); font-size: 14px; }
.lorebook-usage-card p { margin: 6px 0 0; font-size: 12px; }
.lorebook-usage-card details { margin-top: 10px; }
.lorebook-usage-card summary { cursor: pointer; color: var(--df-accent-strong); font-size: 12px; }
.lorebook-usage-card ul { display: grid; gap: 7px; margin: 8px 0 0; padding-left: 18px; }
.lorebook-usage-card li { display: grid; gap: 2px; font-size: 12px; overflow-wrap: anywhere; }
.lorebook-usage-card li span { color: var(--df-text-muted); }
.lorebook-usage-state { grid-column: 1 / -1; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
@media (max-width: 760px) { .lorebook-usage-summary { grid-template-columns: 1fr; } }
</style>
