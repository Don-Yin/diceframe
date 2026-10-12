<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, apiBlob, errorMessage } from '@/api/client'
import type { BatchDeleteGamesResponse, GameMutationResponse, GamesResponse, GameSummary } from '@/api/types'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { useLocale } from '@/composables/useLocale'
import { clearCurrentGame, rememberCurrentGame } from '@/stores/gameContext'
import { NIcon, NDrawer, NDrawerContent } from 'naive-ui'
import {
  BookOutline, HourglassOutline, PeopleOutline, DiceOutline, TrophyOutline,
  CompassOutline, EnterOutline, RefreshOutline, DownloadOutline, TrashOutline,
  SparklesOutline,
  LinkOutline,
} from '@vicons/ionicons5'
import AssistantPanel from '@/components/AssistantPanel.vue'
import PeerConnectModal from '@/features/peer/PeerConnectModal.vue'
import AssistantGreetingBubble from './AssistantGreetingBubble.vue'
import { useAssistant } from '@/composables/useAssistant'
import { ruleSceneUrl } from '@/composables/useBackgroundImages'
import { resolveGameSceneImageUrl, revokeSceneImageUrl, sceneImageStyle } from '@/api/sceneImages'
import { getRendezvousConfig } from '@/api/peer'
import { sortGames, type SaveSortMode } from './saveSorting'

const router = useRouter()
const assistantOpen = ref(false)
const peerModalOpen = ref(false)
const { stop: stopAssistant } = useAssistant()
watch(assistantOpen, (open) => { if (!open) stopAssistant() })

const toast = useToast()
const { confirm } = useConfirm()
const { locale, t } = useLocale()

const games = ref<GameSummary[]>([])
const peerEntryVisible = ref(false)
const saveSort = ref<SaveSortMode>('recent')
const sortedGames = computed(() => sortGames(games.value, saveSort.value, locale.value))
const sceneImageUrls = ref<Record<string, string>>({})
const error = ref('')
function setError(e: unknown) { error.value = errorMessage(e) }
const busy = ref(false)
const selected = ref<string[]>([])

const activeGames = computed(() => games.value.filter(g => stateClass(g.state) === 'badge-active').length)
const playerCount = computed(() => games.value.reduce((sum, g) => sum + Number(g.player_count || 0), 0))
const roundCount = computed(() => games.value.reduce((sum, g) => sum + Number(g.round_number || 0), 0))
const latestScene = computed(() => sortedGames.value.find(g => g.scene)?.scene || t('noScene'))
const statItems = computed(() => [
  { key: 'saves', value: games.value.length, label: t('totalSaves'), icon: BookOutline },
  { key: 'active', value: activeGames.value, label: t('activeGames'), icon: HourglassOutline },
  { key: 'players', value: playerCount.value, label: t('playerSlots'), icon: PeopleOutline },
  { key: 'rounds', value: roundCount.value, label: t('totalRounds'), icon: DiceOutline },
  { key: 'scene', value: latestScene.value, label: t('latestScene'), icon: TrophyOutline, wide: true },
])

async function load() {
  error.value = ''
  try {
    const r = await api<GamesResponse>('/games')
    games.value = r.games || []
    const previous = sceneImageUrls.value
    const entries = await Promise.all(games.value.map(async game => [
      game.game_key,
      await resolveGameSceneImageUrl(game.game_key, String(game.rule_id || '')),
    ] as const))
    sceneImageUrls.value = Object.fromEntries(entries)
    for (const url of Object.values(previous)) revokeSceneImageUrl(url)
  } catch (e: unknown) { setError(e) }
}

async function loadPeerEntryVisibility() {
  peerEntryVisible.value = false
  try {
    const config = await getRendezvousConfig()
    peerEntryVisible.value = config.entry_visible === true
  } catch {
    // Fail closed: an unavailable Hub cannot establish a new rendezvous session.
  }
}

function play(key: string) {
  if (key) {
    const g = games.value.find(item => item.game_key === key)
    rememberCurrentGame(key, g?.world_name || '')
    router.push({ name: 'play', query: { game: key } })
  } else router.push({ name: 'create' })
}

async function remove(key: string) {
  const ok = await confirm({ title: t('deleteSaveTitle'), content: t('deleteSaveContent'), positiveText: t('deleteSaveTitle'), type: 'error' })
  if (!ok) return
  busy.value = true
  try {
    await api<unknown>(`/games/${encodeURIComponent(key)}`, { method: 'DELETE' })
    toast.success(t('deleted'))
    clearCurrentGame(key)
    await load()
  } catch (e: unknown) { setError(e) } finally { busy.value = false }
}

async function exportGame(key: string) {
  try {
    const r = await apiBlob(`/games/${encodeURIComponent(key)}/export`)
    const blob = await r.blob()
    const dispo = r.headers.get('Content-Disposition') || ''
    const m = dispo.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i)
    const baseName = games.value.find(g => g.game_key === key)?.world_name || 'save'
    const filename = m ? decodeURIComponent(m[1]) : `${baseName.replace(/[^A-Za-z0-9_\-]/g, '_')}.json`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
    toast.success(t('exported'))
  } catch (e: unknown) { setError(e) }
}

async function exportAll() {
  if (!games.value.length) { toast.info(t('noSavesToExport')); return }
  toast.info(`${t('exportStarting')} ${games.value.length}...`)
  for (const g of sortedGames.value) {
    await exportGame(g.game_key)
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  toast.success(t('exportDone'))
}

const saveImportInput = ref<HTMLInputElement | null>(null)

async function onImportSave(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  busy.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const r = await api<{ ok?: boolean; game_key?: string; error?: string; player_access_closed?: boolean }>('/games/import', {
      method: 'POST',
      body: form,
    })
    if (!r.ok) throw new Error(r.error || t('importFailed'))
    toast.success(t('saveImported', { name: r.game_key || '' }))
    // Room passwords never travel with a save: a protected game arrives closed.
    if (r.player_access_closed) toast.warning(t('importClosedPlayerAccess'))
    await load()
  } catch (e: unknown) { setError(e) } finally { busy.value = false; input.value = '' }
}

async function resetGame(key: string) {
  const ok = await confirm({ title: t('resetTitle'), content: t('resetContent'), positiveText: t('resetTitle'), type: 'warning' })
  if (!ok) return
  busy.value = true
  try {
    const r = await api<GameMutationResponse>(`/games/${encodeURIComponent(key)}/reset`, { method: 'POST' })
    if (!r.ok) throw new Error(r.error || t('resetFailed'))
    toast.success(`${t('resetDone')} ${r.seed_code || ''}`)
    await load()
  } catch (e: unknown) { setError(e) } finally { busy.value = false }
}

async function restartGame(key: string) {
  const ok = await confirm({ title: t('restartTitle'), content: t('restartContent'), positiveText: t('restartTitle'), type: 'warning' })
  if (!ok) return
  busy.value = true
  try {
    const r = await api<GameMutationResponse>(`/games/${encodeURIComponent(key)}/restart`, { method: 'POST' })
    if (!r.ok) throw new Error(r.error || t('restartFailed'))
    toast.success(`${t('restartDone')} ${r.seed_code || ''}`)
    await load()
  } catch (e: unknown) { setError(e) } finally { busy.value = false }
}

async function batchRemove() {
  if (!selected.value.length) return
  const ok = await confirm({ title: t('batchDeleteTitle'), content: t('batchDeleteContent', { count: selected.value.length }), positiveText: t('deleteSelected'), type: 'error' })
  if (!ok) return
  busy.value = true
  try {
    const r = await api<BatchDeleteGamesResponse>('/games/batch-delete', { method: 'POST', body: JSON.stringify({ game_keys: selected.value }) })
    const deleted = r.deleted?.length || 0
    const failed = r.failed?.length || 0
    toast.success(t('batchDeleted', { deleted, failed: failed ? t('failedCount', { count: failed }) : '' }))
    for (const key of selected.value) clearCurrentGame(key)
    selected.value = []
    await load()
  } catch (e: unknown) { setError(e) } finally { busy.value = false }
}

function selectAll() { selected.value = games.value.map(g => g.game_key) }
function selectInvert() {
  const set = new Set(selected.value)
  selected.value = games.value.filter(g => !set.has(g.game_key)).map(g => g.game_key)
}
function clearSelection() { selected.value = [] }

function stateClass(s?: string) {
  return (s === 'active_action' || s === 'active_judgment' || s === 'waiting') ? 'badge-active' : 'badge-ended'
}
function stateLabel(s?: string) {
  const labels: Record<string, string> = {
    active_action: t('stateActiveAction'),
    active_judgment: t('stateActiveJudgment'),
    waiting: t('stateWaiting'),
    ended: t('stateEnded'),
    paused: t('statePaused'),
    creating: t('stateCreating'),
  }
  return (s && labels[s]) || s || t('stateUnknown')
}

function gameSceneStyle(game: GameSummary): Record<string, string> {
  return sceneImageStyle(sceneImageUrls.value[game.game_key] || ruleSceneUrl(String(game.rule_id || '')))
}

onMounted(() => {
  void load()
  void loadPeerEntryVisibility()
})
onBeforeUnmount(() => {
  for (const url of Object.values(sceneImageUrls.value)) revokeSceneImageUrl(url)
})
</script>

<template>
  <section class="view overview-page">
    <div class="overview-layout">
      <div class="overview-main">
        <header class="overview-hero">
      <div>
        <span class="section-kicker">{{ t('overviewKicker') }}</span>
        <h1>{{ t('overviewTitle') }}</h1>
        <p>{{ t('overviewSubtitle') }}</p>
      </div>
      <div class="overview-actions">
        <button v-if="peerEntryVisible" class="peer-launch-button" @click="peerModalOpen = true"><NIcon :component="LinkOutline" />{{ t('peerDirectConnect') }}</button>
        <button @click="saveImportInput?.click()" :disabled="busy">{{ t('importSave') }}</button>
        <input ref="saveImportInput" type="file" accept=".zip" @change="onImportSave" hidden>
        <button class="success" @click="play('')">{{ t('createAdventure') }}</button>
      </div>
    </header>

    <section class="overview-stats" :aria-label="t('archiveStats')">
      <article v-for="item in statItems" :key="item.key" :class="{ wide: item.wide }">
        <NIcon :component="item.icon" />
        <div><strong>{{ item.value }}</strong><span>{{ item.label }}</span></div>
      </article>
    </section>

    <p v-if="error" class="error-banner">{{ error }}</p>

    <section v-if="games.length" class="adventure-library">
      <header class="library-heading">
        <div class="library-heading-copy"><span><i />{{ t('recentAdventures') }}</span><small>{{ games.length }} {{ t('totalSaves') }}</small></div>
        <div class="library-heading-actions">
          <label class="save-sort-field">
            <span>{{ t('saveSort') }}</span>
            <select v-model="saveSort" class="save-sort-select" :aria-label="t('saveSort')">
              <option value="recent">{{ t('saveSortRecent') }}</option>
              <option value="oldest">{{ t('saveSortOldest') }}</option>
              <option value="name">{{ t('saveSortName') }}</option>
              <option value="round">{{ t('saveSortRound') }}</option>
            </select>
          </label>
          <button @click="selectAll">{{ t('selectAll') }}</button>
          <button @click="selectInvert">{{ t('invertSelection') }}</button>
          <button @click="clearSelection" :disabled="!selected.length">{{ t('clearSelection') }}</button>
          <button @click="exportAll" :disabled="busy">{{ t('exportAll') }}</button>
          <button v-if="selected.length" class="danger" @click="batchRemove" :disabled="busy">{{ t('deleteSelected') }} {{ selected.length }}</button>
        </div>
      </header>
      <div class="game-grid">
        <article v-for="g in sortedGames" :key="g.game_key" class="game-card">
          <div class="game-card-art" :style="gameSceneStyle(g)" aria-hidden="true" />
          <div class="game-card-cover">
            <span class="cover-sigil"><NIcon :component="CompassOutline" /></span>
            <label class="game-select compact">
              <input type="checkbox" :value="g.game_key" v-model="selected" :aria-label="t('chooseSave')">
              <span>{{ t('choose') }}</span>
            </label>
            <div class="game-card-badges">
              <small class="badge" :class="stateClass(g.state)">{{ stateLabel(g.state) }}</small>
              <small v-if="g.solo_mode" class="badge badge-active">{{ t('solo') }}</small>
              <small v-else class="badge">{{ t('multiplayer') }}</small>
            </div>
          </div>
          <div class="game-card-body">
            <h2 :title="g.world_name || g.game_key">{{ g.world_name || g.game_key }}</h2>
            <p class="scene-line">{{ g.scene || t('notStarted') }}</p>
            <div class="game-card-meta">
              <span>{{ t('roundPrefix') }}{{ g.round_number || 0 }}{{ t('roundSuffix') }}</span>
              <span>{{ t('players') }} {{ g.player_count || 0 }}/{{ g.max_players || 0 }}</span>
              <span>LLM {{ g.total_llm_calls || 0 }}</span>
            </div>
            <p class="muted meta">{{ t('token') }} {{ g.total_tokens || 0 }}<span v-if="g.seed_code"> · {{ t('seed') }} <code>{{ g.seed_code }}</code></span></p>
            <div class="game-card-actions">
              <button class="success game-card-enter" @click="play(g.game_key)"><span>{{ t('enter') }}</span><NIcon :component="EnterOutline" /></button>
              <div class="game-card-tools">
                <button @click="exportGame(g.game_key)"><NIcon :component="DownloadOutline" />{{ t('export') }}</button>
                <button @click="restartGame(g.game_key)" :disabled="busy"><NIcon :component="RefreshOutline" />{{ t('restart') }}</button>
                <button @click="resetGame(g.game_key)" :disabled="busy"><NIcon :component="CompassOutline" />{{ t('reset') }}</button>
                <button class="danger" @click="remove(g.game_key)" :disabled="busy"><NIcon :component="TrashOutline" />{{ t('delete') }}</button>
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section v-else class="empty-panel">
      <h2>{{ t('emptyTitle') }}</h2>
      <p class="muted">{{ t('emptySubtitle') }}</p>
      <button class="success" @click="play('')">{{ t('createAdventure') }}</button>
    </section>
      </div>

      <NDrawer
        v-model:show="assistantOpen"
        placement="right"
        :width="440"
        style="max-width: 100vw;"
        class="overview-assistant-drawer"
      >
        <NDrawerContent :native-scrollbar="false" body-content-style="padding: 0; height: 100%;">
          <AssistantPanel @close="assistantOpen = false" />
        </NDrawerContent>
      </NDrawer>
      <PeerConnectModal v-model:show="peerModalOpen" />
      <AssistantGreetingBubble @open="assistantOpen = true" />
      <button
        class="overview-assistant-fab"
        @click="assistantOpen = true"
        :aria-label="t('toggleAssistant')"
      >
        <NIcon :component="SparklesOutline" size="20" />
      </button>
    </div>
  </section>
</template>

<style scoped>
.overview-layout {
  position: relative;
  min-height: 0;
}
.overview-main {
  width: 100%;
  min-width: 0;
}

/* 抽屉内容铺满,助手面板自身撑满高度 */
.overview-assistant-drawer :deep(.n-drawer-content) {
  padding: 0;
}
.overview-assistant-drawer :deep(.n-drawer-body),
.overview-assistant-drawer :deep(.n-drawer-body-content-wrapper) {
  height: 100%;
  padding: 0;
}
.overview-assistant-drawer :deep(.n-drawer-header) {
  display: none;
}
.overview-assistant-drawer :deep(.assistant-panel) {
  height: 100%;
}

/* 侧边悬浮圆钮:AI 助手入口 */
.overview-assistant-fab {
  position: fixed;
  right: 18px;
  bottom: calc(24px + env(safe-area-inset-bottom));
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  padding: 0;
  border: 1px solid color-mix(in srgb, var(--df-accent-strong) 45%, var(--df-border-soft));
  border-radius: 50%;
  background: var(--df-surface-2);
  color: var(--df-accent-strong);
  cursor: pointer;
  box-shadow: var(--df-shadow);
}
.overview-assistant-fab:hover {
  border-color: var(--df-interactive-strong);
  color: var(--df-interactive-strong);
}

@media (max-width: 700px) {
  .overview-assistant-fab {
    right: 14px;
    bottom: calc(72px + env(safe-area-inset-bottom));
    width: 44px;
    height: 44px;
  }

  /* Mobile keeps the entry silent: no onboarding/help speech bubble. */
  .overview-assistant-fab::before,
  .overview-assistant-fab::after {
    display: none !important;
    content: none !important;
  }
}
</style>
