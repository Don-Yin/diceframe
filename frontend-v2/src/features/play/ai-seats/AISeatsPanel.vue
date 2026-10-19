<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { api } from '@/api/client'
import type { Player } from '@/api/types'
import Modal from '@/components/ui/Modal.vue'
import { useLocale } from '@/composables/useLocale'
import { aiSeatCopy, aiSeatReason } from './copy'
import type { AISeatResponse, AISeatSettings, AISeatStyle } from './types'
import { parseAISeatResponse } from './types'

const props = defineProps<{ gameKey: string; runId: string; players: Player[]; isGm: boolean; preview?: boolean; round?: number }>()
const emit = defineEmits<{ changed: []; 'set-control': [uid: string, mode: 'human']; attention: [count: number] }>()
const { locale } = useLocale()
const copy = computed(() => aiSeatCopy[locale.value])
const visible = computed(() => props.isGm && !props.preview && Boolean(props.gameKey))
const state = ref<AISeatResponse | null>(null), error = ref(''), busy = ref(false)
const editorOpen = ref(false), editedUid = ref<string | undefined>(), editRevision = ref(0)
const provider = ref(''), model = ref(''), style = ref<AISeatStyle | ''>('')
let epoch = 0, timer: ReturnType<typeof setInterval> | undefined
const base = computed(() => `/games/${encodeURIComponent(props.gameKey)}/ai-seats`)
const providerRef = computed(() => provider.value || state.value?.defaults.provider_ref || state.value?.application?.provider_ref || '')
const models = computed(() => state.value?.providers.find(p => p.id === providerRef.value)?.models || [])
const editorName = computed(() => editedUid.value === undefined ? copy.value.defaults : props.players.find(p => p.user_id === editedUid.value)?.character_name || editedUid.value)
const attentionCount = computed(() => props.players.reduce((count, player) => {
  if (player.control?.mode !== 'ai') return count
  const seat = state.value?.seats[player.user_id]
  if (!seat) return count
  const outcome = seat.last_outcome
  const currentOutcome = outcome && (props.round === undefined || outcome.round === props.round)
  return count + (!seat.ready || Boolean(currentOutcome && (outcome.status === 'fallback' || outcome.status === 'skipped')) ? 1 : 0)
}, 0))
function reason(code: string) { return aiSeatReason(copy.value, code) }

async function refresh() {
  if (!visible.value) return
  const current = epoch, url = base.value
  try {
    const result = parseAISeatResponse(await api<unknown>(url))
    if (current === epoch && visible.value) {
      const outcomes = (value: AISeatResponse) => JSON.stringify(Object.entries(value.seats).map(([uid, seat]) => [uid, seat.last_outcome]))
      const changed = state.value && outcomes(state.value) !== outcomes(result)
      state.value = result; if (!editorOpen.value) error.value = ''
      if (changed) emit('changed')
    }
  } catch { if (current === epoch) error.value = copy.value.error }
}
watch(attentionCount, count => emit('attention', count), { immediate: true })
watch([visible, () => props.gameKey, () => props.runId], () => {
  emit('attention', 0)
  epoch++; state.value = null; editorOpen.value = false; error.value = ''; busy.value = false
  if (timer) clearInterval(timer)
  if (visible.value) { void refresh(); timer = setInterval(() => { if (!busy.value) void refresh() }, 4000) }
}, { immediate: true })
onUnmounted(() => { epoch++; if (timer) clearInterval(timer); emit('attention', 0) })

function open(uid?: string) {
  if (!state.value) return
  editedUid.value = uid
  const settings = uid === undefined ? state.value.defaults : state.value.seats[uid]?.settings || {}
  provider.value = settings.provider_ref || ''; model.value = settings.model || ''; style.value = settings.style || ''
  editRevision.value = state.value.revision; error.value = ''; editorOpen.value = true
}
function resetProvider() { model.value = '' }
async function save() {
  const current = epoch, url = `${base.value}/${editedUid.value === undefined ? 'defaults' : `seats/${encodeURIComponent(editedUid.value)}`}`
  busy.value = true; error.value = ''
  const settings: AISeatSettings = { provider_ref: provider.value || null, model: model.value.trim() || null, style: style.value || null }
  try {
    const result = parseAISeatResponse(await api<unknown>(url, { method: 'PUT', body: JSON.stringify({ settings, expected_revision: editRevision.value }) }))
    if (current === epoch) { state.value = result; editorOpen.value = false; emit('changed') }
  } catch { if (current === epoch) error.value = copy.value.error }
  finally { if (current === epoch) busy.value = false }
}
async function retry(uid: string) {
  const current = epoch, url = `${base.value}/seats/${encodeURIComponent(uid)}/retry`
  busy.value = true; error.value = ''
  try {
    await api(url, { method: 'POST', body: '{}' })
    if (current === epoch) { await refresh(); emit('changed') }
  } catch { if (current === epoch) error.value = copy.value.error }
  finally { if (current === epoch) busy.value = false }
}
</script>

<template>
  <section v-if="visible" class="panel ai-seats" data-testid="ai-seats">
    <div class="ai-seats-heading"><h2>{{ copy.title }}</h2><button :disabled="!state || busy" @click="open()">{{ copy.defaults }}</button></div>
    <p class="hint">{{ copy.combat }}</p>
    <p v-if="!state && !error" role="status">{{ copy.loading }}</p>
    <p v-if="error" role="alert">{{ error }} <button @click="refresh">{{ copy.reload }}</button></p>
    <ul v-if="state" class="ai-seat-list">
      <li v-for="player in players" :key="player.user_id">
        <div class="ai-seat-heading"><strong>{{ player.character_name || player.user_id }}</strong><button :data-testid="`configure-${player.user_id}`" :disabled="busy" @click="open(player.user_id)">{{ copy.configure }}</button></div>
        <template v-if="state.seats[player.user_id]">
          <p>{{ state.seats[player.user_id]!.provider_name || '—' }} · {{ state.seats[player.user_id]!.model || '—' }} · {{ copy[state.seats[player.user_id]!.style || 'character'] }}</p>
          <small>{{ state.seats[player.user_id]!.inherits ? copy.inherited : copy.override }}</small>
          <p v-if="!state.seats[player.user_id]!.ready" class="error" role="status">{{ reason(state.seats[player.user_id]!.reason) }}</p>
          <template v-if="player.control?.mode === 'ai'">
            <p v-if="state.seats[player.user_id]!.generating" role="status">{{ copy.generating }}</p>
            <p v-else-if="state.seats[player.user_id]!.last_outcome" role="status">
              {{ copy.round }} {{ state.seats[player.user_id]!.last_outcome!.round }}:
              {{ state.seats[player.user_id]!.last_outcome!.status === 'fallback' ? copy.fallback : state.seats[player.user_id]!.last_outcome!.status === 'added' ? copy.added : copy.skipped }}
              <span v-if="state.seats[player.user_id]!.last_outcome!.reason"> · {{ reason(state.seats[player.user_id]!.last_outcome!.reason) }}</span>
            </p>
            <p v-if="state.seats[player.user_id]!.retry_reason" class="hint">{{ reason(state.seats[player.user_id]!.retry_reason) }}</p>
            <div class="ai-seat-actions">
              <button :data-testid="`retry-${player.user_id}`" :disabled="busy || state.seats[player.user_id]!.generating || !state.seats[player.user_id]!.ready || Boolean(state.seats[player.user_id]!.retry_reason)" @click="retry(player.user_id)">{{ copy.retry }}</button>
              <button :disabled="busy" @click="emit('set-control', player.user_id, 'human')">{{ copy.stop }}</button>
            </div>
          </template>
        </template>
      </li>
    </ul>
    <Modal v-if="editorOpen" :title="`${copy.title} · ${editorName}`" dialog-class="ai-seat-dialog" @close="editorOpen = false">
      <form @submit.prevent="save">
        <label>{{ copy.provider }}<select v-model="provider" data-testid="provider" @change="resetProvider"><option value="">{{ editedUid === undefined ? copy.inheritApp : copy.inheritGame }}</option><option v-for="item in state?.providers" :key="item.id" :value="item.id">{{ item.name }}</option><option v-if="provider && !state?.providers.some(p => p.id === provider)" :value="provider" disabled>{{ provider }} · {{ copy.unavailable }}</option></select></label>
        <label>{{ copy.model }}<select v-if="models.length" v-model="model" data-testid="model"><option value="">{{ editedUid === undefined ? copy.inheritApp : copy.inheritGame }}</option><option v-for="item in models" :key="item" :value="item">{{ item }}</option><option v-if="model && !models.includes(model)" :value="model" disabled>{{ model }} · {{ copy.unavailable }}</option></select><input v-else v-model="model" data-testid="model" maxlength="160" :placeholder="editedUid === undefined ? copy.inheritApp : copy.inheritGame" /></label>
        <label>{{ copy.style }}<select v-model="style" data-testid="style"><option value="">{{ editedUid === undefined ? copy.inheritApp : copy.inheritGame }}</option><option v-for="item in state?.styles" :key="item" :value="item">{{ copy[item] }}</option></select></label>
        <p class="hint">{{ copy.unchanged }}</p>
        <p v-if="error" role="alert">{{ error }}</p>
        <div class="ai-seat-actions"><button type="submit" data-testid="save" :disabled="busy">{{ copy.save }}</button><button type="button" :disabled="busy" @click="editorOpen = false">{{ copy.cancel }}</button><button type="button" :disabled="busy" @click="open(editedUid)">{{ copy.reload }}</button></div>
      </form>
    </Modal>
  </section>
</template>

<style scoped>
.ai-seats-heading,.ai-seat-heading,.ai-seat-actions { display:flex; align-items:center; gap:.6rem; flex-wrap:wrap; }
.ai-seats-heading,.ai-seat-heading { justify-content:space-between; }
.ai-seats p { margin:.45rem 0; overflow-wrap:anywhere; }
.hint,.ai-seats small { opacity:.7; font-size:.85rem; }
.ai-seat-list { list-style:none; padding:0; margin:0; }
.ai-seat-list li { border-top:1px solid var(--border-color, #8883); padding:.8rem 0; }
.error,[role=alert] { color:var(--error-color, #bd5252); }
label { display:flex; flex-direction:column; gap:.4rem; margin-bottom:.8rem; }
select,input { width:100%; min-width:0; padding:.55rem; border-radius:.4rem; }
button { padding:.35rem .55rem; white-space:normal; }
form { max-width:100%; }
</style>
