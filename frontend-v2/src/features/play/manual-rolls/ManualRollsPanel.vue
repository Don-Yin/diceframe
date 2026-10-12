<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import Modal from '@/components/ui/Modal.vue'
import { useLocale } from '@/composables/useLocale'
import { useManualRolls } from './useManualRolls'
import type { ManualRollComparison, ManualRollPurpose, ManualRollRequest, ManualRollVisibility } from './types'

const props = defineProps<{
  gameKey: string; runId: string; actorId: string; isGm: boolean; lastActivity?: string; preview?: boolean; delegate?: boolean
  players: Array<{ user_id: string; character_name: string }>
}>()
const { locale } = useLocale()
const zh = computed(() => locale.value.startsWith('zh'))
const copy = computed(() => zh.value ? {
  title: '手动投掷', request: '发起投掷', retry: '重试', empty: '手动投掷',
  purpose: '用途', free: '自由投掷', check: '规则检定', contest: '对抗比较', target: '目标值', targetPlaceholder: '例如：15', comparison: '判定方向', auto: '按当前规则自动', atLeast: '达到目标即成功', atMost: '不超过目标即成功',
  pending: '等待投掷', resolved: '已完成', cancelled: '已取消', rollFor: '代投',
  gmOverride: 'GM 代投', requestNotice: 'GM 请求你进行一次投掷，请确认后提交结果。',
  cancel: '取消请求', pendingRoll: '待投掷', dialog: '发起手动投掷', label: '说明',
  labelPlaceholder: '例如：察觉检定', formula: '骰子公式', formulaHint: '例如 d20、d20+2、2d6+1；自由投掷只记录骰值，规则检定会显示成败。', visibility: '可见范围',
  party: '全队可见', private: '仅目标可见', targets: '投掷角色', later: '稍后',
  send: '发送请求', sending: '发送中…', roll: '投掷', rolling: '投掷中…',
  chooseTarget: '请至少选择一名投掷角色。',
  tellAi: '将结果告知 AI', aiAlwaysIncluded: '规则检定与对抗比较的结果始终会告知 AI。',
} : {
  title: 'Manual rolls', request: 'Request roll', retry: 'Retry', empty: 'Manual roll',
  pending: 'Pending', resolved: 'Resolved', cancelled: 'Cancelled', rollFor: 'Roll for',
  gmOverride: 'GM override', requestNotice: 'The GM requested a roll from you. Confirm it to submit the result.',
  cancel: 'Cancel request', pendingRoll: 'Pending roll', dialog: 'Request a manual roll',
  purpose: 'Purpose', free: 'Free roll', check: 'Rule check', contest: 'Contest', target: 'Target', targetPlaceholder: 'e.g. 15', comparison: 'Success direction', auto: 'Use current rules', atLeast: 'Meet or exceed target', atMost: 'Stay at or below target',
  label: 'Label', labelPlaceholder: 'e.g. Perception', formula: 'Dice formula', formulaHint: 'Examples: d20, d20+2, 2d6+1. Free rolls only record the result; checks also show success or failure.',
  visibility: 'Visibility', party: 'Party', private: 'Targets only', targets: 'Targets',
  later: 'Later', send: 'Send request', sending: 'Sending…', roll: 'Roll',
  rolling: 'Rolling…', chooseTarget: 'Select at least one target.',
  tellAi: 'Tell the AI', aiAlwaysIncluded: 'Rule check and contest results are always shared with the AI.',
})
const viewerIsGm = computed(() => props.isGm && !props.preview)
const rolls = useManualRolls(toRef(props, 'gameKey'), toRef(props, 'runId'), toRef(props, 'actorId'), viewerIsGm, toRef(props, 'lastActivity'))
const visibleRequests = rolls.visibleRequests
const activeRequest = rolls.activeRequest
const composerOpen = ref(false), formula = ref('d20'), label = ref(''), purpose = ref<ManualRollPurpose>('free'), target = ref<number | null>(null), comparison = ref<ManualRollComparison>('auto'), visibility = ref<ManualRollVisibility>('party'), targetUids = ref<string[]>([])
const includeInAi = ref(false)
const busy = ref(false), submitError = ref(''), draftOperationId = ref('')
const canCreate = computed(() => viewerIsGm.value)
const canAct = computed(() => !props.preview || Boolean(props.delegate))
const reopenable = computed(() => rolls.pendingForActor.value.filter(item => !rolls.activeRequest.value || item.id !== rolls.activeRequest.value.id))

function resetComposer() { formula.value = 'd20'; label.value = ''; purpose.value = 'free'; target.value = null; comparison.value = 'auto'; visibility.value = 'party'; targetUids.value = props.players.map(player => player.user_id); includeInAi.value = false; submitError.value = ''; draftOperationId.value = '' }
function openComposer() { resetComposer(); composerOpen.value = true }
function toggleTarget(uid: string) { targetUids.value = targetUids.value.includes(uid) ? targetUids.value.filter(item => item !== uid) : [...targetUids.value, uid] }
async function create() {
  if (!targetUids.value.length) { submitError.value = copy.value.chooseTarget; return }
  busy.value = true; submitError.value = ''
  if (purpose.value === 'check' && (target.value === null || !Number.isInteger(target.value))) { submitError.value = copy.value.targetPlaceholder; return }
  // 检定/对抗由服务端强制收录，前端不发送该开关；自由投掷按勾选发送严格布尔。
  const includeInAiContext = purpose.value === 'free' ? includeInAi.value : undefined
  try { draftOperationId.value = await rolls.create({ formula: formula.value, label: label.value, purpose: purpose.value, target: target.value, comparison: comparison.value, include_in_ai_context: includeInAiContext, target_uids: targetUids.value, visibility: visibility.value, operation_id: draftOperationId.value || undefined }); composerOpen.value = false; draftOperationId.value = '' }
  catch (error: unknown) { submitError.value = error instanceof Error ? error.message : String(error) }
  finally { busy.value = false }
}
async function resolve(request: ManualRollRequest, targetUid = props.actorId) { busy.value = true; try { await rolls.roll(request, targetUid) } catch (error: unknown) { submitError.value = error instanceof Error ? error.message : String(error) } finally { busy.value = false } }
async function cancel(request: ManualRollRequest) { busy.value = true; try { await rolls.cancel(request) } catch (error: unknown) { submitError.value = error instanceof Error ? error.message : String(error) } finally { busy.value = false } }
function verdictText(value?: string) {
  if (zh.value) return value === 'success' ? '成功' : value === 'failure' ? '失败' : value === 'winner' ? '胜者' : value === 'loss' ? '落败' : ''
  return value === 'success' ? 'success' : value === 'failure' ? 'failure' : value === 'winner' ? 'winner' : value === 'loss' ? 'loss' : ''
}
function resultText(request: ManualRollRequest) { return Object.entries(request.results).map(([uid, result]) => `${request.target_names[uid] || uid}: ${result.total}${result.target == null ? '' : ` / ${result.target}`}${verdictText(result.verdict) ? ` · ${verdictText(result.verdict)}` : ''}`).join(' · ') }
function statusText(status: ManualRollRequest['status']) { return copy.value[status] }
function purposeText(value?: ManualRollPurpose) { return value === 'check' ? copy.value.check : value === 'contest' ? copy.value.contest : copy.value.free }
</script>

<template>
  <section v-if="canCreate || visibleRequests.length" class="manual-rolls panel" data-testid="manual-rolls">
    <div class="manual-rolls-header"><div><small>GM</small><h3>{{ copy.title }}</h3></div><button v-if="canCreate" type="button" class="primary" @click="openComposer">{{ copy.request }}</button></div>
    <div class="manual-roll-list">
      <article v-for="request in visibleRequests" :key="request.id" class="manual-roll-card">
        <strong>{{ request.label || copy.empty }} · {{ request.formula }} · {{ purposeText(request.purpose) }}</strong>
        <span>{{ statusText(request.status) }} · {{ request.target_uids.map(uid => request.target_names[uid] || uid).join(', ') }}</span>
        <p v-if="resultText(request)">{{ resultText(request) }}</p>
        <div v-if="viewerIsGm && request.status === 'pending'" class="manual-roll-actions">
          <button v-for="uid in request.target_uids" :key="uid" type="button" :disabled="busy || preview || Boolean(request.results[uid])" @click="resolve(request, uid)">{{ copy.gmOverride }} · {{ request.target_names[uid] || uid }}</button>
          <button type="button" class="danger-quiet" :disabled="busy || preview" @click="cancel(request)">{{ copy.cancel }}</button>
        </div>
      </article>
    </div>
    <button v-for="request in reopenable" :key="`reopen-${request.id}`" type="button" class="manual-roll-badge" @click="rolls.reopen(request.id)">{{ copy.pendingRoll }}：{{ request.label || request.formula }}</button>
  </section>

  <Modal v-if="composerOpen" :title="copy.dialog" @close="composerOpen = false">
    <label>{{ copy.label }} <input v-model="label" maxlength="200" :placeholder="copy.labelPlaceholder" /></label>
    <label>{{ copy.formula }} <input v-model="formula" placeholder="d20 + 2" /><small class="manual-roll-field-hint">{{ copy.formulaHint }}</small></label>
    <label>{{ copy.purpose }} <select v-model="purpose"><option value="free">{{ copy.free }}</option><option value="check">{{ copy.check }}</option><option value="contest">{{ copy.contest }}</option></select></label>
    <template v-if="purpose === 'check'"><label>{{ copy.target }} <input v-model.number="target" type="number" min="1" max="10000" :placeholder="copy.targetPlaceholder" /></label><label>{{ copy.comparison }} <select v-model="comparison"><option value="auto">{{ copy.auto }}</option><option value="at_least">{{ copy.atLeast }}</option><option value="at_most">{{ copy.atMost }}</option></select></label></template>
    <label>{{ copy.visibility }} <select v-model="visibility"><option value="party">{{ copy.party }}</option><option value="private">{{ copy.private }}</option></select></label>
    <label v-if="purpose === 'free'">{{ copy.tellAi }} <input v-model="includeInAi" type="checkbox" data-testid="manual-roll-include-ai" /></label>
    <small v-else class="manual-roll-field-hint">{{ copy.aiAlwaysIncluded }}</small>
    <fieldset class="manual-roll-targets"><legend>{{ copy.targets }}</legend><label v-for="player in players" :key="player.user_id" class="form-check"><input type="checkbox" :checked="targetUids.includes(player.user_id)" @change="toggleTarget(player.user_id)" /> <span>{{ player.character_name || player.user_id }}</span></label></fieldset>
    <p v-if="submitError" class="muted">{{ submitError }}</p>
    <template #actions><button :disabled="busy" @click="composerOpen = false">{{ copy.later }}</button><button class="primary" :disabled="busy" @click="create">{{ busy ? copy.sending : copy.send }}</button></template>
  </Modal>

  <Modal v-if="activeRequest" :title="activeRequest.label || copy.title" @close="rolls.dismiss(activeRequest.id)">
    <p class="manual-roll-notice" role="status" aria-live="assertive">{{ copy.requestNotice }}</p>
    <p>{{ copy.roll }} {{ activeRequest.formula }}</p>
    <p v-if="submitError" class="muted">{{ submitError }}</p>
    <template #actions><button @click="rolls.dismiss(activeRequest.id)">{{ copy.later }}</button><button class="primary" :disabled="busy || !canAct" @click="resolve(activeRequest)">{{ busy ? copy.rolling : copy.roll }}</button></template>
  </Modal>
</template>

<style scoped>
.manual-rolls {
  display: grid;
  gap: 10px;
  min-width: 0;
  padding: 12px;
  border-color: rgb(190 151 74 / 38%);
  background: linear-gradient(145deg, rgb(31 39 46 / 96%), rgb(18 27 34 / 98%));
  box-shadow: inset 0 1px rgb(255 255 255 / 4%);
}

.manual-rolls-header {
  display: flex;
  min-width: 0;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.manual-rolls-header > div {
  display: flex;
  min-width: 0;
  gap: 8px;
  align-items: center;
}

.manual-rolls-header small {
  display: grid;
  flex: 0 0 26px;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 1px solid #b99a5a;
  border-radius: 50%;
  color: #e5c87f;
  font-size: 10px;
  font-weight: 800;
}

.manual-rolls-header h3 {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: #efe2bd;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.manual-rolls button {
  min-height: 34px;
  white-space: nowrap;
}

.manual-rolls-header .primary {
  flex: 0 0 auto;
  padding: 6px 10px;
  border-color: #63bbb8;
  background: linear-gradient(180deg, #204c55, #173740);
  color: #dcffff;
}

.manual-roll-list {
  display: grid;
  gap: 8px;
}

.manual-roll-card {
  display: grid;
  gap: 5px;
  padding: 9px 10px;
  border: 1px solid rgb(190 151 74 / 28%);
  border-radius: 9px;
  background: rgb(10 18 25 / 38%);
}

.manual-roll-card > span {
  color: var(--df-text-muted);
  font-size: 12px;
}

.manual-roll-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.manual-roll-actions button {
  flex: 1 1 auto;
  padding: 5px 8px;
}

.danger-quiet {
  color: #f0a1a1;
}

.manual-roll-badge {
  width: 100%;
  text-align: left;
}

.manual-roll-error {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 0;
  padding: 8px 10px;
  border: 1px solid rgb(210 123 102 / 38%);
  border-radius: 7px;
  background: rgb(88 38 35 / 22%);
  color: #e7b5a4;
  font-size: 12px;
}

.manual-roll-error span {
  min-width: 0;
  flex: 1 1 120px;
}

.manual-roll-error button {
  min-height: 28px;
  padding: 4px 9px;
}

.manual-rolls input,
.manual-rolls select {
  max-width: 100%;
}

.manual-roll-field-hint {
  display: block;
  margin-top: 4px;
  color: var(--df-text-muted);
  font-size: 11px;
  line-height: 1.45;
}

.manual-roll-targets {
  display: grid;
  gap: 6px;
  margin: 10px 0;
  padding: 10px;
  border: 1px solid rgb(190 151 74 / 35%);
  border-radius: 8px;
  background: rgb(10 18 25 / 35%);
}

.manual-roll-targets legend {
  padding: 0 5px;
  color: #efe2bd;
  font-size: 13px;
  font-weight: 700;
}

.manual-roll-targets .form-check {
  display: flex;
  min-height: 36px;
  box-sizing: border-box;
  width: 100%;
  gap: 9px;
  align-items: center;
  justify-content: flex-start;
  margin: 0;
  padding: 7px 9px;
  border: 1px solid rgb(122 153 158 / 28%);
  border-radius: 6px;
  background: rgb(18 35 43 / 70%);
  color: var(--df-text-secondary);
  cursor: pointer;
}

.manual-roll-targets .form-check:hover {
  border-color: rgb(99 187 184 / 72%);
  background: rgb(28 55 63 / 82%);
}

.manual-roll-targets .form-check input[type='checkbox'] {
  flex: 0 0 18px;
  width: 18px;
  height: 18px;
  margin: 0;
  appearance: none;
  border: 1px solid #aa8a4d;
  border-radius: 4px;
  background: #0c1a21;
  cursor: pointer;
}

.manual-roll-targets .form-check input[type='checkbox']:checked {
  border-color: #e0b65d;
  background: #d99b45 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='m3 8 3 3 7-7' fill='none' stroke='%23122128' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") center / 13px 13px no-repeat;
}

.manual-roll-targets .form-check input[type='checkbox']:focus-visible {
  outline: 2px solid #63bbb8;
  outline-offset: 2px;
}
</style>
