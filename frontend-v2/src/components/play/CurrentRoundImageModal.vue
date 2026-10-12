<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { GameDetail, LogEntry, Player, ScenePanel } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import Modal from '@/components/ui/Modal.vue'
import { analyzeStoryboard } from '@/api/generatedImages'

const props = defineProps<{ open: boolean; gameKey: string; detail: GameDetail; log: LogEntry[]; players?: Player[]; autoStoryboard?: boolean }>()
const emit = defineEmits<{
  close: []
  generate: [payload: { prompt: string; round: number; panels: unknown[]; panel_count?: number; use_avatar_references: boolean }]
}>()
const { t } = useLocale()
const prompt = ref('')
const targetRound = ref(0)
const useAvatarReferences = ref(false)
// 0 means automatic layout; 1-6 are explicit user-selected panel counts.
const panelCount = ref<number>(0)
const visiblePanelCount = computed(() => panelCount.value > 0 ? panelCount.value : Math.max(1, Math.min(6, panels.value.length || 1)))
const panels = ref<ScenePanel[]>([])
const candidatePanels = ref<ScenePanel[] | null>(null)
const candidatePanelCount = ref<number | null>(null)
const hasStoryboardDraft = ref(false)
const panelError = ref('')
const analyzing = ref(false)
const analysisMessage = ref('')
const storyboardEnabled = computed(() => props.autoStoryboard !== false)
const analyzeButtonLabel = computed(() => {
  if (analyzing.value) return t('storyboardAnalyzingHint')
  if (panelCount.value > 0) return t('storyboardAnalyzeCount', { count: panelCount.value })
  return hasStoryboardDraft.value ? t('storyboardReanalyze') : t('storyboardAnalyze')
})

const uploadAvatarIds = computed(() => new Set(
  (props.players || [])
    .filter(player => {
      const portrait = player.character_sheet?.portrait
        || (player as Player & { portrait?: { kind?: string; asset_id?: string } }).portrait
      return portrait?.kind === 'upload' && !!portrait.asset_id
    })
    .map(player => player.user_id),
))
const uploadAvatarCount = computed(() => uploadAvatarIds.value.size)
// Avatar references are independent from storyboard mode. Single-image
// generation can still use explicitly identifiable uploaded portraits.
const canUseAvatarReferences = computed(() => uploadAvatarIds.value.size > 0)

const NARRATION_LIMIT = 1600
function toggleParticipant(panel: ScenePanel, userId: string, checked: boolean) {
  const selected = new Set(panel.participants || [])
  if (checked) selected.add(userId)
  else selected.delete(userId)
  panel.participants = [...selected]
}

function participantsText(panel: ScenePanel): string {
  return (panel.participants || []).join(', ')
}

function setParticipantsText(panel: ScenePanel, value: string) {
  panel.participants = value.split(/[,，]/).map(item => item.trim()).filter(Boolean)
}

function draftPrompt(): string {
  const latest = [...props.log].reverse().find(item => String(item.gm_response || '').trim())
  const round = Number(latest?.round ?? Math.max(0, Number(props.detail.round_number || 0) - 1))
  targetRound.value = round
  useAvatarReferences.value = false
  const scene = String(props.detail.scene || t('unknownScene'))
  const narration = String(latest?.gm_response || '').trim().slice(0, NARRATION_LIMIT)
  const savedPanels = Array.isArray(latest?.scene_panels)
    ? latest.scene_panels as ScenePanel[]
    : []
  hasStoryboardDraft.value = savedPanels.length > 0
  candidatePanels.value = null
  candidatePanelCount.value = null
  panels.value = savedPanels.length
    ? savedPanels.map(panel => ({
      participants: [...(panel.participants || [])],
      location: String(panel.location || scene),
      description: String(panel.description || ''),
    }))
    : [{ participants: [], location: scene, description: narration || scene }]
  panelCount.value = storyboardEnabled.value ? 0 : 1
  panelError.value = ''
  // Content only: style and composition wording is composed server-side from
  // imagegen_style_prefix / imagegen_manual_rules / imagegen_manual_prompt.
  return [scene, narration].map(part => part.trim()).filter(Boolean).join('\n')
}

watch(panelCount, (count) => {
  candidatePanels.value = null
  candidatePanelCount.value = null
  analysisMessage.value = ''
  const target = Number(count)
  if (!target) {
    panelError.value = ''
    return
  }
  const normalizedTarget = Math.max(1, Math.min(6, target))
  panelCount.value = normalizedTarget
  while (panels.value.length < normalizedTarget) {
    panels.value.push({ participants: [], location: String(props.detail.scene || t('unknownScene')), description: '' })
  }
  // Keep hidden panels when decreasing the requested count; users can restore
  // the previous value without losing their edits.
  panelError.value = ''
})

watch(() => props.open, (open) => {
  if (!open) return
  prompt.value = draftPrompt()
}, { immediate: true })

function generate() {
  if (!props.gameKey || !prompt.value.trim()) return
  if (panelCount.value === 0) {
    panelError.value = ''
    emit('generate', {
      prompt: prompt.value.trim(), round: targetRound.value, panels: [],
      use_avatar_references: useAvatarReferences.value && canUseAvatarReferences.value,
    })
    return
  }
  const normalized = panels.value.slice(0, panelCount.value).map(panel => ({
    participants: Array.isArray(panel.participants) ? panel.participants.map(item => String(item).trim()).filter(Boolean) : [],
    location: String(panel.location || '').trim(),
    description: String(panel.description || '').trim(),
  }))
  if (normalized.some(panel => !panel.location || !panel.description)) {
    panelError.value = t('storyboardPanelRequired')
    return
  }
  panelError.value = ''
  emit('generate', {
    prompt: prompt.value.trim(),
    round: targetRound.value,
    panels: normalized,
    panel_count: panelCount.value,
    use_avatar_references: useAvatarReferences.value && canUseAvatarReferences.value,
  })
}

function close() {
  emit('close')
}

async function analyze() {
  if (analyzing.value) return
  analyzing.value = true
  analysisMessage.value = t('storyboardAnalyzingHint')
  panelError.value = ''
  const requestedCount = panelCount.value > 0 ? panelCount.value : undefined
  try {
    const result = await analyzeStoryboard(props.gameKey, targetRound.value, requestedCount)
    if (!result.ok || !Array.isArray(result.panels) || !result.panels.length) throw new Error(result.error || 'storyboard-analysis-failed')
    if (requestedCount && result.panels.length !== requestedCount) {
      throw new Error(t('storyboardPanelCountMismatch', { count: requestedCount, actual: result.panels.length }))
    }
    candidatePanels.value = (result.panels as ScenePanel[]).map(panel => ({
      participants: [...(panel.participants || [])],
      location: String(panel.location || ''),
      description: String(panel.description || ''),
    }))
    candidatePanelCount.value = requestedCount ?? 0
    analysisMessage.value = t('storyboardCandidateReady')
  } catch (error) {
    analysisMessage.value = ''
    panelError.value = error instanceof Error ? error.message : String(error)
  } finally {
    analyzing.value = false
  }
}

function applyCandidate() {
  if (!candidatePanels.value?.length) return
  const fixedCount = candidatePanelCount.value && candidatePanelCount.value > 0
    ? candidatePanelCount.value
    : null
  if (fixedCount && candidatePanels.value.length !== fixedCount) {
    panelError.value = t('storyboardPanelCountMismatch', { count: fixedCount, actual: candidatePanels.value.length })
    return
  }
  panels.value = candidatePanels.value.map(panel => ({
    participants: [...(panel.participants || [])],
    location: panel.location,
    description: panel.description,
  }))
  panelCount.value = fixedCount ?? Math.max(1, Math.min(6, panels.value.length))
  hasStoryboardDraft.value = true
  candidatePanels.value = null
  candidatePanelCount.value = null
}
</script>

<template>
  <Modal v-if="open" :title="t('generateRoundImage')" @close="close">
    <p class="muted">{{ t('roundImagePromptHint') }}</p>
    <textarea v-model="prompt" rows="8" :placeholder="t('roundImagePromptPlaceholder')" />
    <div class="storyboard-editor">
      <div class="storyboard-header">
         <span v-if="!storyboardEnabled" class="muted">{{ t('storyboardAutomatic') }}</span>
         <button v-if="storyboardEnabled" type="button" :disabled="analyzing" @click="analyze">{{ analyzeButtonLabel }}</button>
         <button v-if="candidatePanels" type="button" class="primary" @click="applyCandidate">{{ t('storyboardApplyCandidate') }}</button>
      </div>
      <p v-if="storyboardEnabled && !hasStoryboardDraft && !candidatePanels" class="muted">{{ t('storyboardNotAnalyzed') }}</p>
       <p v-if="analyzing || analysisMessage" class="muted" data-testid="storyboard-analysis-status">{{ analysisMessage }}</p>
      <div v-if="candidatePanels" class="storyboard-candidate" data-testid="storyboard-candidate">
        <strong>{{ t('storyboardCandidateTitle') }}</strong>
        <article v-for="(panel, index) in candidatePanels" :key="`candidate-${index}`" class="storyboard-candidate-panel">
          <span>{{ t('storyboardPanelLabel', { index: index + 1 }) }} · {{ panel.location }}</span>
          <small>{{ (panel.participants || []).join(', ') || t('storyboardNoParticipants') }}</small>
          <p>{{ panel.description }}</p>
        </article>
      </div>
      <div v-for="(panel, index) in panels.slice(0, visiblePanelCount)" v-show="panelCount > 0" :key="index" class="storyboard-panel">
        <strong>{{ t('storyboardPanelLabel', { index: index + 1 }) }}</strong>
        <input v-model="panel.location" :placeholder="t('storyboardLocationPlaceholder')" />
        <input :value="participantsText(panel)" :placeholder="t('storyboardParticipantsEditPlaceholder')" @input="setParticipantsText(panel, ($event.target as HTMLInputElement).value)" />
        <div class="storyboard-participants">
          <label v-for="player in players || []" :key="player.user_id">
            <input type="checkbox" :checked="(panel.participants || []).includes(player.user_id)" @change="toggleParticipant(panel, player.user_id, ($event.target as HTMLInputElement).checked)">
            <span>{{ player.character_name || player.user_id }}</span>
          </label>
          <span v-if="!players?.length" class="muted">{{ t('storyboardParticipantsPlaceholder') }}</span>
        </div>
        <textarea v-model="panel.description" rows="3" :placeholder="t('storyboardDescriptionPlaceholder')" />
      </div>
      <p v-if="panelError" class="panel-error">{{ panelError }}</p>
    </div>
    <label class="avatar-reference-toggle" :class="{ disabled: !canUseAvatarReferences }">
      <input v-model="useAvatarReferences" type="checkbox" :disabled="!canUseAvatarReferences">
      <span>{{ t('useAvatarReferences') }}</span>
    </label>
    <p v-if="canUseAvatarReferences" class="muted avatar-reference-hint">
      {{ t('avatarReferenceUploadNotice', { count: uploadAvatarCount }) }}
    </p>
    <p v-else class="muted avatar-reference-hint">
      {{ t('avatarReferenceUnavailableNotice') }}
    </p>
    <template #actions>
      <button @click="close">{{ t('close') }}</button>
      <button class="primary" :disabled="!prompt.trim()" @click="generate">{{ t('generateImage') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
textarea { width: 100%; min-height: 150px; resize: vertical; }
.avatar-reference-toggle { display: inline-flex; align-items: center; gap: 8px; margin-top: 10px; cursor: pointer; }
.avatar-reference-toggle.disabled { cursor: not-allowed; opacity: 0.62; }
.avatar-reference-toggle input { width: 16px; height: 16px; accent-color: var(--df-interactive); }
.avatar-reference-hint { margin: 2px 0 0; font-size: 0.85em; }
.smart-storyboard-hint { margin: 10px 0 0; }
.storyboard-editor { margin-top: 14px; border-top: 1px solid var(--df-border); padding-top: 12px; }
.storyboard-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.storyboard-header select { margin-left: 6px; min-width: 56px; }
.storyboard-panel { display: grid; gap: 6px; margin: 8px 0; padding: 10px; border: 1px solid var(--df-border); border-radius: 6px; }
.storyboard-panel input, .storyboard-panel textarea { width: 100%; box-sizing: border-box; }
.storyboard-panel textarea { min-height: 56px; }
.storyboard-participants { display: flex; flex-wrap: wrap; gap: 6px 14px; }
.storyboard-participants label { display: inline-flex; align-items: center; gap: 5px; cursor: pointer; }
.storyboard-participants input { width: 16px; height: 16px; accent-color: var(--df-interactive); }
.panel-error { color: var(--df-danger, #b42318); margin: 8px 0 0; }
.storyboard-candidate { margin: 10px 0; padding: 10px; border: 1px dashed var(--df-interactive); border-radius: 6px; background: color-mix(in srgb, var(--df-interactive) 7%, transparent); }
.storyboard-candidate-panel { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--df-border); }
.storyboard-candidate-panel span, .storyboard-candidate-panel small { display: block; }
.storyboard-candidate-panel small { color: var(--df-text-muted); margin-top: 2px; }
.storyboard-candidate-panel p { margin: 4px 0 0; }
</style>
