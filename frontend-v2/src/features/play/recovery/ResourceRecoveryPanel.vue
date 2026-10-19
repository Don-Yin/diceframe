<script setup lang="ts">
import { computed, ref, toRef, useId, watch } from 'vue'
import Modal from '@/components/ui/Modal.vue'
import { useLocale } from '@/composables/useLocale'
import { resourceRecoveryCopy } from './resourceRecoveryCopy'
import { useResourceRecovery } from './useResourceRecovery'
import type { RecoveryKind, RecoveryReceipt, RecoverySource } from './resourceRecoveryTypes'

const props = defineProps<{ gameKey: string; actorId: string; isGm: boolean; refreshKey?: unknown; readonly?: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const { locale } = useLocale()
const copy = computed(() => resourceRecoveryCopy(locale.value))
const viewerKey = computed(() => `${props.actorId}:${props.isGm}:${props.readonly}`)
const { snapshot, loading, busy, error, uncertain, completed, refresh, submit, retry } = useResourceRecovery(toRef(props, 'gameKey'), toRef(props, 'refreshKey'), viewerKey, () => emit('changed'))
const open = ref(false)
const recipient = ref('')
const healer = ref('')
const skill = ref('')
const rewardResource = ref('sanity')
const rewardAmount = ref('1d3')
const rewardReason = ref('')
const intermission = ref('')
const id = useId()
const gm = computed(() => props.isGm && snapshot.value?.is_gm === true)
const actorUid = computed(() => gm.value ? recipient.value : props.actorId)
const actor = computed(() => snapshot.value?.actors?.find(row => row.uid === actorUid.value))
const healerActor = computed(() => snapshot.value?.actors?.find(row => row.uid === healer.value))
const disabled = computed(() => busy.value || loading.value || uncertain.value || props.readonly || Boolean(snapshot.value?.blockers?.length))
const unavailableReason = computed(() => !actor.value?.eligible ? actor.value?.reason || copy.value.ineligible : '')
const rewardValue = computed(() => {
  const value = rewardAmount.value.trim()
  if (['1d3', '1d6', '1d10'].includes(value)) return value
  const number = Number(value)
  return value && Number.isInteger(number) && number >= -99 && number <= 99 && number !== 0 ? number : null
})
const sources = computed(() => [...(snapshot.value?.sources || [])].reverse())
const receipts = computed(() => [...(snapshot.value?.receipts || [])].reverse())
function actorName(uid?: string) { return snapshot.value?.actors?.find(row => row.uid === uid)?.name || uid || '' }
function kindName(kind: RecoveryKind) { return copy.value[kind] }
function statusName(source: RecoverySource) { return copy.value[source.status] }
function rollSummary(receipt: RecoveryReceipt) {
  const rolls = receipt.rolls
  if (!rolls || typeof rolls !== 'object' || Array.isArray(rolls)) return ''
  const values = rolls as Record<string, unknown>
  return [
    ['check', 'd100'], ['threshold', copy.value.threshold],
    ['recovery', copy.value.recoveryRoll], ['loss', copy.value.lossRoll],
  ].flatMap(([key, label]) => typeof values[key!] === 'number' && Number.isFinite(values[key!]) ? [`${label}: ${values[key!]}`] : []).join(' · ')
}
function canClaim(source: RecoverySource) {
  return source.status === 'approved' && ['luck', 'reward'].includes(source.kind) && (gm.value || source.actor_uid === props.actorId)
}
function request(kind: 'overnight' | 'therapy') {
  if (disabled.value || !actor.value?.eligible) return
  if (kind === 'therapy' && (!healer.value || !skill.value)) return
  void submit('request', { kind, actor_uid: actorUid.value, ...(kind === 'therapy' ? { healer_uid: healer.value, skill_id: skill.value } : {}) })
}
function authorizeReward() {
  if (disabled.value || !gm.value || !actor.value?.eligible || rewardValue.value === null || !rewardReason.value.trim()) return
  void submit('reward', { actor_uid: actorUid.value, resource_key: rewardResource.value, resource_delta: rewardValue.value, reason: rewardReason.value.trim() })
}
function show() { open.value = true; void refresh() }
defineExpose({ open: show })

watch([snapshot, () => props.actorId], () => {
  const actors = snapshot.value?.actors || []
  if (!actors.some(row => row.uid === recipient.value)) recipient.value = actors.find(row => row.uid === props.actorId)?.uid || actors[0]?.uid || ''
  if (!actors.some(row => row.uid === healer.value && row.skills.length)) healer.value = actors.find(row => row.skills.length)?.uid || ''
  const rows = snapshot.value?.intermissions || []
  if (!rows.some(row => row.id === intermission.value)) intermission.value = rows.at(-1)?.id || ''
})
watch(healerActor, row => { if (!row?.skills.some(entry => entry.id === skill.value)) skill.value = row?.skills[0]?.id || '' })
watch([() => props.gameKey, viewerKey], () => { open.value = false })
</script>

<template>
  <button v-if="snapshot?.supported || error" class="resource-recovery-entry" type="button" data-testid="resource-recovery-open" :aria-expanded="open" @click="show">{{ copy.title }}</button>
  <Modal v-if="open" :title="copy.title" dialog-class="resource-recovery-dialog" :close-on-backdrop="true" @close="open = false">
    <div class="resource-recovery-body">
      <div class="resource-recovery-toolbar"><span v-if="loading" role="status">{{ copy.loading }}</span><button type="button" :disabled="loading || busy" @click="refresh">{{ copy.refresh }}</button></div>
      <div v-if="error" class="resource-recovery-notice warn" role="alert"><p>{{ error }}</p><p v-if="uncertain">{{ copy.uncertain }}</p><button v-if="uncertain && !readonly" type="button" data-testid="recovery-retry" :disabled="busy" @click="retry">{{ copy.retry }}</button></div>
      <p v-if="completed && !error" class="resource-recovery-notice good" role="status">{{ copy.submitted }}</p>
      <template v-if="snapshot?.supported">
        <p class="resource-recovery-policy">{{ snapshot.policy.policy === 'coc_light' ? copy.light : copy.strict }}</p>
        <p v-if="snapshot.policy.luck_recovery === 'check'" class="resource-recovery-policy">{{ copy.luckHint }}</p>
        <div v-if="snapshot.blockers?.length" class="resource-recovery-notice warn" role="status"><p>{{ snapshot.message || copy.unavailable }}</p><p v-for="reason in snapshot.blockers" :key="reason">{{ reason }}</p></div>
        <p v-if="readonly" class="resource-recovery-policy">{{ copy.readonly }}</p>
        <section v-else class="resource-recovery-section">
          <h3>{{ copy.newRequest }}</h3>
          <label v-if="gm" class="resource-recovery-field" :for="`${id}-recipient`">{{ copy.recipient }}<select :id="`${id}-recipient`" v-model="recipient" :disabled="disabled"><option v-for="row in snapshot.actors" :key="row.uid" :value="row.uid">{{ row.name }}</option></select></label>
          <p v-if="unavailableReason" class="warn" role="status">{{ unavailableReason }}</p>
          <p class="muted">{{ copy.requestHint }}</p>
          <div v-for="action in snapshot.actions" :key="action.id" class="resource-recovery-action">
            <div><strong>{{ kindName(action.id) }}</strong><span class="muted">SAN · {{ action.amount }}</span></div>
            <template v-if="action.id === 'therapy'">
              <div class="resource-recovery-grid">
                <label class="resource-recovery-field" :for="`${id}-healer`">{{ copy.healer }}<select :id="`${id}-healer`" v-model="healer" data-testid="recovery-healer" :disabled="disabled"><option value="">{{ copy.choose }}</option><option v-for="row in snapshot.actors.filter(entry => entry.skills.length)" :key="row.uid" :value="row.uid">{{ row.name }}</option></select></label>
                <label class="resource-recovery-field" :for="`${id}-skill`">{{ copy.skill }}<select :id="`${id}-skill`" v-model="skill" :disabled="disabled || !healer"><option v-for="entry in healerActor?.skills || []" :key="entry.id" :value="entry.id">{{ entry.name }}</option></select></label>
              </div>
              <p v-if="!healer || !skill" class="muted">{{ copy.missingHealer }}</p>
            </template>
            <button type="button" :data-testid="`recovery-request-${action.id}`" :disabled="disabled || !actor?.eligible || (action.id === 'therapy' && (!healer || !skill))" @click="request(action.id)">{{ copy.request }}{{ kindName(action.id) }}</button>
          </div>
        </section>

        <section class="resource-recovery-section">
          <h3>{{ copy.requests }}</h3>
          <p v-if="!sources.length" class="muted">{{ copy.noSources }}</p>
          <article v-for="source in sources" :key="source.source_id" class="resource-recovery-record">
            <div class="resource-recovery-record-title"><strong>{{ actorName(source.actor_uid) }} · {{ kindName(source.kind) }}</strong><span class="muted">{{ statusName(source) }}</span></div>
            <p v-if="source.healer_uid" class="muted">{{ copy.healer }}: {{ actorName(source.healer_uid) }}</p>
            <p v-if="source.reason">{{ source.reason }}</p>
            <div v-if="!readonly" class="resource-recovery-buttons">
              <template v-if="gm && source.status === 'pending'"><button type="button" :data-testid="`recovery-approve-${source.source_id}`" :disabled="disabled" @click="submit('approve', { source_id: source.source_id })">{{ copy.approve }}</button><button type="button" :disabled="busy || loading || uncertain" @click="submit('reject', { source_id: source.source_id })">{{ copy.reject }}</button></template>
              <button v-if="canClaim(source)" type="button" :data-testid="`recovery-claim-${source.source_id}`" :disabled="disabled" @click="submit('claim', { source_id: source.source_id })">{{ copy.claim }}</button>
            </div>
          </article>
        </section>

        <details v-if="gm && !readonly" class="resource-recovery-section" data-testid="recovery-gm-tools">
          <summary>{{ copy.gmTools }}</summary>
          <div class="resource-recovery-gm-content">
            <h3>{{ copy.reward }}</h3>
            <p class="muted">{{ copy.recipient }}: {{ actorName(actorUid) }}</p>
            <div class="resource-recovery-grid">
              <label class="resource-recovery-field" :for="`${id}-resource`">{{ copy.resource }}<select :id="`${id}-resource`" v-model="rewardResource" :disabled="disabled"><option value="sanity">{{ copy.sanity }}</option><option value="luck">{{ copy.luck }}</option></select></label>
              <label class="resource-recovery-field" :for="`${id}-amount`">{{ copy.amount }}<input :id="`${id}-amount`" v-model="rewardAmount" :disabled="disabled" placeholder="1d3 / 1d6 / 1d10 / -99…99" maxlength="8"></label>
            </div>
            <label class="resource-recovery-field" :for="`${id}-reason`">{{ copy.reason }}<textarea :id="`${id}-reason`" v-model="rewardReason" :disabled="disabled" rows="2" maxlength="240" /></label>
            <button type="button" data-testid="recovery-authorize-reward" :disabled="disabled || !actor?.eligible || rewardValue === null || !rewardReason.trim()" @click="authorizeReward">{{ copy.authorize }}</button>
            <template v-if="snapshot.policy.luck_recovery === 'check'">
              <h3>{{ copy.luck }}</h3>
              <label v-if="snapshot.intermissions.length" class="resource-recovery-field" :for="`${id}-intermission`">{{ copy.intermission }}<select :id="`${id}-intermission`" v-model="intermission" :disabled="disabled"><option v-for="row in snapshot.intermissions" :key="row.id" :value="row.id">#{{ row.round }}</option></select></label>
              <p v-else class="muted">{{ copy.noIntermission }}</p>
              <button type="button" data-testid="recovery-open-luck" :disabled="disabled || !intermission" @click="submit('luck', { intermission_id: intermission })">{{ copy.openLuck }}</button>
            </template>
          </div>
        </details>

        <details class="resource-recovery-section" :open="receipts.length > 0">
          <summary>{{ copy.receipts }}</summary>
          <p v-if="!receipts.length" class="muted">{{ copy.noReceipts }}</p>
          <article v-for="receipt in receipts" :key="receipt.source_id" class="resource-recovery-record">
            <strong>{{ actorName(receipt.actor_uid) }} · {{ kindName(receipt.kind) }}</strong>
            <span>{{ receipt.resource_key === 'sanity' ? copy.sanity : copy.luck }}: {{ receipt.before }} → {{ receipt.after }}</span>
            <span v-if="rollSummary(receipt)" class="muted">{{ rollSummary(receipt) }}</span>
            <span :class="receipt.resource_delta < 0 ? 'warn' : receipt.resource_delta === 0 ? 'muted' : 'good'">{{ receipt.fumble ? copy.fumble : receipt.success === false ? copy.checkFailed : receipt.resource_delta === 0 ? copy.unchanged : copy.success }}</span>
          </article>
        </details>
      </template>
    </div>
    <template #actions><button type="button" @click="open = false">{{ copy.close }}</button></template>
  </Modal>
</template>

<style scoped>
.resource-recovery-entry { width: 100%; min-height: 34px; margin-block-start: 8px; padding: 7px 10px; text-align: start; font-size: 12px; }
:global(.dialog.resource-recovery-dialog) { width: min(640px, calc(100vw - 30px)); max-height: calc(100dvh - 30px); display: flex; flex-direction: column; min-height: 0; overflow: hidden; gap: 12px; }
:global(.dialog.resource-recovery-dialog > header), :global(.dialog.resource-recovery-dialog > .actions) { flex-shrink: 0; }
.resource-recovery-body { display: grid; flex: 1 1 auto; gap: 12px; overflow-y: auto; min-height: 0; overscroll-behavior: contain; }
.resource-recovery-toolbar { display: flex; align-items: center; justify-content: flex-end; gap: 8px; }
.resource-recovery-policy, .resource-recovery-body p { margin: 0; line-height: 1.6; overflow-wrap: anywhere; }
.resource-recovery-policy { color: var(--df-text-secondary); font-size: 12px; }
.resource-recovery-section { display: grid; min-width: 0; gap: 10px; padding: 12px; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-md); }
.resource-recovery-section h3 { margin: 0; font-size: 14px; }
.resource-recovery-section summary { cursor: pointer; font-weight: 600; }
.resource-recovery-action, .resource-recovery-gm-content { display: grid; gap: 10px; min-width: 0; }
.resource-recovery-action > div:first-child, .resource-recovery-record-title { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 6px; }
.resource-recovery-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.resource-recovery-field { display: grid; min-width: 0; gap: 5px; font-size: 12px; }
.resource-recovery-field input, .resource-recovery-field select, .resource-recovery-field textarea { width: 100%; min-width: 0; box-sizing: border-box; }
.resource-recovery-record { display: grid; gap: 6px; padding-block: 10px; border-bottom: 1px solid var(--df-border-soft); font-size: 12px; }
.resource-recovery-record:last-child { border-bottom: 0; }
.resource-recovery-buttons { display: flex; gap: 8px; flex-wrap: wrap; }
.resource-recovery-body button { min-height: 34px; white-space: normal; overflow-wrap: anywhere; }
.resource-recovery-notice { display: grid; gap: 8px; padding: 10px; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-md); }
@media (max-width: 480px) { .resource-recovery-grid { grid-template-columns: minmax(0, 1fr); } .resource-recovery-section { padding: 10px; } }
</style>
