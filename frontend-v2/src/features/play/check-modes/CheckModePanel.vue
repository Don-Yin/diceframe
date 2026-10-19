<script setup lang="ts">
import { computed, onUnmounted, ref, toRaw, watch } from 'vue'
import { api } from '@/api/client'
import Modal from '@/components/ui/Modal.vue'
import { useLocale } from '@/composables/useLocale'
import { modeCopy, modeText } from './copy'
import { parseModeResponse, type CheckMode, type ModeResponse, type ModeSeat } from './types'

const props = defineProps<{ gameKey: string; runId: string; actorId: string; isGm: boolean; preview?: boolean; delegate?: boolean }>()
const emit = defineEmits<{ changed: []; status: [value: { pendingCount: number; error: string }] }>()
const { locale } = useLocale()
const copy = computed(() => modeCopy[locale.value])
const visible = computed(() => Boolean(props.gameKey && (props.isGm || props.actorId)))
const writable = computed(() => !props.preview || props.delegate)
const state = ref<ModeResponse | null>(null), busy = ref(false), error = ref(''), toolOpen = ref(false)
const editing = ref<{ seat: ModeSeat; operation: 'request' | 'grant' | 'reject'; revision: number; run: string } | null>(null)
const mode = ref<CheckMode>('advantage'), reason = ref('')
const seats = computed(() => state.value?.seats.filter(s => s.kind) || [])
const supportedSeats = computed(() => seats.value.filter(s => s.blocked_reason !== 'unsupported'))
const gm = computed(() => Boolean(state.value?.is_gm ?? props.isGm))
const displaySeats = computed(() => gm.value ? supportedSeats.value : supportedSeats.value.filter(s => s.uid === props.actorId))
const pendingSeats = computed(() => displaySeats.value.filter(s => s.request?.status === 'pending'))
const ownPending = computed(() => pendingSeats.value.some(s => s.uid === props.actorId))
const toolVisible = computed(() => visible.value && Boolean(error.value || displaySeats.value.length))
const base = computed(() => `/games/${encodeURIComponent(props.gameKey)}/check-modes`)
let epoch = 0, timer: ReturnType<typeof setInterval> | undefined
function text(code: string) { return modeText(copy.value, code) }
function emitStatus() { emit('status', { pendingCount: pendingSeats.value.length, error: error.value }) }
function label(seat: ModeSeat, value: string) {
  if (!value) return copy.value.normal
  return seat.kind === 'coc_bonus_penalty' ? (value === 'advantage' ? copy.value.bonus : copy.value.penalty) : text(value)
}
async function refresh() {
  if (!visible.value) return
  const current = epoch
  try {
    const result = parseModeResponse(await api<unknown>(base.value))
    if (current === epoch) { state.value = result; if (!editing.value) error.value = ''; emitStatus() }
  } catch {
    if (current === epoch) { error.value = copy.value.error; emitStatus() }
  }
}
watch([visible, () => props.gameKey, () => props.runId, () => props.actorId, () => props.isGm, writable], () => {
  epoch++; state.value = null; editing.value = null; toolOpen.value = false; error.value = ''; busy.value = false; emitStatus()
  if (timer) clearInterval(timer)
  if (visible.value) { void refresh(); timer = setInterval(() => { if (!busy.value) void refresh() }, 4000) }
}, { immediate: true })
onUnmounted(() => { epoch++; if (timer) clearInterval(timer) })
function openTool() { if (toolVisible.value) toolOpen.value = true }
function closeTool() { toolOpen.value = false; editing.value = null }
function editSeat(seat: ModeSeat, operation: 'request' | 'grant' | 'reject') {
  if (!state.value) return
  editing.value = { seat: structuredClone(toRaw(seat)), operation, revision: state.value.revision, run: state.value.run_id }
  mode.value = seat.request?.mode || 'advantage'; reason.value = operation === 'grant' ? seat.request?.reason || '' : ''
  error.value = ''
}
defineExpose({ open: openTool })
async function mutate(seat: ModeSeat, operation: string, revision: number, run: string, draftReason = '', draftMode: string | undefined = undefined) {
  const current = epoch
  busy.value = true; error.value = ''
  try {
    const response = parseModeResponse(await api<unknown>(`${base.value}/seats/${encodeURIComponent(seat.uid)}/${operation}`, {
      method: 'POST', body: JSON.stringify({ expected_revision: revision, run_id: run, context_id: seat.context_id,
        ...(draftMode ? { mode: draftMode } : {}), ...(draftReason ? { reason: draftReason } : {}) }),
    }))
    if (current === epoch) { state.value = response; editing.value = null; emit('changed'); emitStatus() }
  } catch { if (current === epoch) { error.value = copy.value.error; emitStatus() } }
  finally { if (current === epoch) busy.value = false }
}
function submit() {
  const edit = editing.value
  if (edit && reason.value.trim()) void mutate(edit.seat, edit.operation, edit.revision, edit.run, reason.value.trim(), edit.operation === 'reject' ? undefined : mode.value)
}
</script>

<template>
  <section v-if="toolVisible" class="check-mode-panel" data-testid="check-modes">
    <button type="button" class="check-mode-trigger" data-testid="check-mode-trigger" :aria-expanded="toolOpen" @click="openTool">
      <span>{{ copy.tool }}</span>
      <span v-if="gm && pendingSeats.length" class="pending-badge" data-testid="check-mode-pending-badge">{{ pendingSeats.length }}</span>
      <span v-else-if="ownPending" class="pending-state" data-testid="check-mode-own-pending">{{ copy.pending }}</span>
    </button>
    <Modal v-if="toolOpen" :title="copy.title" dialog-class="check-mode-dialog" close-test-id="check-mode-close" @close="closeTool">
      <p class="hint">{{ copy.hint }}</p>
      <p v-if="error" role="alert">{{ error }} <button type="button" @click="refresh">{{ copy.reload }}</button></p>
      <article v-for="seat in displaySeats" :key="seat.uid">
        <strong>{{ seat.name }}</strong> · <small>{{ text(seat.scope) }}</small>
        <p v-if="seat.request">{{ copy.request }}: {{ label(seat, seat.request.mode) }} · {{ seat.request.reason }} · {{ text(seat.request.status) }}<span v-if="seat.request.decision_reason"> · {{ seat.request.decision_reason }}</span></p>
        <p v-if="seat.grant">{{ copy.grant }}: {{ label(seat, seat.grant.mode) }} · {{ seat.grant.reason }}</p>
        <ul v-if="seat.previews.length"><li v-for="(item, index) in seat.previews" :key="index">{{ item.label }}: {{ label(seat, item.mode) }}<ul v-if="item.sources.length"><li v-for="(source, i) in item.sources" :key="i">{{ text(source.code) }} · {{ label(seat, source.mode) }}<span v-if="source.reason"> · {{ source.reason }}</span></li></ul></li></ul>
        <p v-if="seat.blocked_reason" class="hint">{{ text(seat.blocked_reason) }}</p>
        <div class="actions">
          <button v-if="!gm" type="button" :data-testid="`request-${seat.uid}`" :disabled="busy || !writable || Boolean(seat.blocked_reason)" @click="editSeat(seat, 'request')">{{ copy.request }}</button>
          <template v-else>
            <button type="button" :data-testid="`grant-${seat.uid}`" :disabled="busy || !writable || Boolean(seat.blocked_reason)" @click="editSeat(seat, 'grant')">{{ copy.grant }}</button>
            <button v-if="seat.request?.status === 'pending'" type="button" :disabled="busy || !writable || Boolean(seat.blocked_reason)" @click="editSeat(seat, 'reject')">{{ copy.reject }}</button>
            <button v-if="seat.grant && state" type="button" :disabled="busy || !writable || Boolean(seat.blocked_reason)" @click="mutate(seat, 'clear', state.revision, state.run_id)">{{ copy.clear }}</button>
          </template>
        </div>
      </article>
    </Modal>
    <Modal v-if="editing" :title="`${text(editing.operation)} · ${editing.seat.name}`" dialog-class="check-mode-dialog" @close="editing = null">
      <form @submit.prevent="submit">
        <select v-if="editing.operation !== 'reject'" v-model="mode" aria-label="Mode"><option value="advantage">{{ label(editing.seat, 'advantage') }}</option><option value="disadvantage">{{ label(editing.seat, 'disadvantage') }}</option></select>
        <label>{{ copy.reason }}<textarea v-model="reason" data-testid="mode-reason" required maxlength="500" rows="3" /></label>
        <p v-if="error" role="alert">{{ error }}</p>
        <div class="actions"><button type="submit" :disabled="busy || !reason.trim()">{{ copy.save }}</button><button type="button" :disabled="busy" @click="editing = null">{{ copy.cancel }}</button></div>
      </form>
    </Modal>
  </section>
</template>

<style scoped>
.check-mode-panel { min-width:0; margin:.6rem 0; }
.check-mode-trigger { display:inline-flex; align-items:center; gap:.4rem; }
.pending-badge { min-width:1.25rem; padding:0 .3rem; border-radius:999px; background:var(--df-interactive); color:var(--df-on-accent); text-align:center; }
.pending-state { color:var(--df-text-muted); font-size:.85em; }
article { border-top:1px solid var(--df-border-soft); padding:.6rem 0; overflow-wrap:anywhere; }
p { margin:.4rem 0; } ul { padding-left:1.25rem; } .actions { display:flex; flex-wrap:wrap; gap:.5rem; }
label { display:grid; gap:.35rem; margin:.6rem 0; } textarea,select { width:100%; box-sizing:border-box; } form { min-width:0; }
.hint { color:var(--df-text-muted); font-size:.85rem; }
</style>
