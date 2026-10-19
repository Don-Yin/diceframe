<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useLocale } from '@/composables/useLocale'
import { carryGame, changeStory, downloadRun, generateStory, loadStory, storyError as errorMessage, type AiProgress, type RunStoryState } from './api'

const props = defineProps<{ gameKey: string; revision: number | string; isGm: boolean; lifecycleStatus?: string }>()
const emit = defineEmits<{ changed: [] }>()
const { locale } = useLocale()
const c = (zh: string, en: string) => locale.value === 'zh-CN' ? zh : en
const state = ref<RunStoryState>(), busy = ref(false), error = ref(''), progress = ref<AiProgress>()
const epilogue = ref(''), recap = ref(''), notes = ref(''), consent = ref(false), review = ref(false), confirmed = ref(false)
const carryActors = ref<string[]>([]), nextGame = ref('')
let controller: AbortController | undefined, generation = 0, loadedJob = ''
const finale = computed(() => state.value?.finale)
const preparing = computed(() => (finale.value?.status || props.lifecycleStatus) === 'preparing')
const ended = computed(() => (finale.value?.status || props.lifecycleStatus) === 'ended')
function acceptState(result: RunStoryState) {
  const materialsChanged = result.finale.revision !== state.value?.finale.revision
  state.value = result
  error.value = ''
  if (result.finale.id !== loadedJob || materialsChanged) {
    loadedJob = result.finale.id || ''; epilogue.value = result.finale.epilogue || ''; recap.value = result.finale.recap || ''; notes.value = result.finale.gm_notes || ''; review.value = false; confirmed.value = false
  }
  if (!carryActors.value.length) carryActors.value = Object.keys(result.finale.characters || {})
  nextGame.value = result.carry_deliveries?.find(item => item.status === 'delivered')?.game_key || nextGame.value
}
async function load() {
  const request = ++generation
  try {
    const result = await loadStory(props.gameKey)
    if (request !== generation) return
    acceptState(result)
  } catch (e) { if (request === generation) error.value = errorMessage(e) }
}
async function mutate(action: string, extra: object = {}) {
  busy.value = true; error.value = ''
  generation++
  const key = props.gameKey
  try {
    const result = await changeStory(key, action, { run_id: state.value?.run_id, job_id: finale.value?.id, job_revision: finale.value?.revision, ...extra })
    if (key !== props.gameKey) return false
    if (!result.ok) throw new Error(result.error || 'Operation failed')
    generation++; acceptState(result); emit('changed'); return true
  } catch (e) { if (key === props.gameKey) error.value = errorMessage(e); return false }
  finally { busy.value = false }
}
async function saveMaterials() {
  if (await mutate('materials', { epilogue: epilogue.value, recap: recap.value, gm_notes: notes.value })) { review.value = true; confirmed.value = false }
}
async function generate() {
  if (!consent.value || busy.value) return
  const key = props.gameKey; controller = new AbortController(); busy.value = true; error.value = ''
  try {
    const draft = await generateStory(key, 'finale', { run_id: state.value?.run_id, job_id: finale.value?.id, token_consent: true }, controller.signal, p => { progress.value = p })
    if (key === props.gameKey) { epilogue.value = draft.epilogue || ''; recap.value = draft.recap || ''; review.value = false }
  } catch (e) { if (!controller.signal.aborted) error.value = errorMessage(e) }
  finally { busy.value = false; progress.value = undefined }
}
async function download(character = false, uid = '') { try { await downloadRun(props.gameKey, character, uid) } catch (e) { error.value = errorMessage(e) } }
async function intermission() { await mutate('intermission', { receipt_id: `intermission_${crypto.randomUUID()}` }) }
async function carry() {
  busy.value = true; error.value = ''
  const key = props.gameKey
  try {
    const result = await carryGame(key, { run_id: state.value?.run_id, delivery_id: `next_${finale.value?.id}`, actor_uids: carryActors.value })
    if (key !== props.gameKey) return
    if (!result.ok) throw new Error(result.error || 'Carry failed')
    nextGame.value = result.game_key
  } catch (e) { if (key === props.gameKey) error.value = errorMessage(e) }
  finally { busy.value = false }
}
watch(() => [props.gameKey, props.revision], () => { void load() }, { immediate: true })
watch(() => finale.value?.characters, characters => { if (characters && !carryActors.value.length) carryActors.value = Object.keys(characters) })
watch(() => props.gameKey, () => {
  controller?.abort(); loadedJob = ''; state.value = undefined
  carryActors.value = []; nextGame.value = ''; review.value = false; confirmed.value = false
})
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <section v-if="isGm || preparing || ended" class="run-finale" data-testid="run-finale">
    <h3>{{ ended ? c('本次冒险已结束', 'This adventure has ended') : c('幕间与结团', 'Intermission & finale') }}</h3>
    <template v-if="ended && finale">
      <h4>{{ c('尾声', 'Epilogue') }}</h4><p class="public-text">{{ finale?.epilogue }}</p>
      <h4>{{ c('全程团录', 'Whole-run recap') }}</h4><p class="public-text">{{ finale?.recap }}</p>
      <p>{{ c('本局为只读档案。结算已提交，重试导出不会重新发放成长或奖励。', 'This run is a read-only archive. Retrying export cannot award growth or rewards again.') }}</p>
      <div class="finale-actions"><button @click="download()">{{ c('导出团录', 'Export recap') }}</button><button v-if="finale?.character" @click="download(true)">{{ c('带走我的角色', 'Export my settled character') }}</button></div>
      <details v-if="isGm"><summary>{{ c('结算回执', 'Settlement receipt') }}</summary><pre>{{ finale?.receipt }}</pre></details>
      <details v-if="isGm"><summary>{{ c('角色带入下一次冒险', 'Carry characters to another adventure') }}</summary><p>{{ c('选择结算后的角色，创建同世界的独立自由对局。旧档案保留；新局可重新邀请玩家，不继承旧邀请凭据、秘密或剧情计划。', 'Create a separate free game in the same world with settled characters. The old archive remains; invitations, secrets and story progress are not carried.') }}</p><label v-for="(_, uid) in finale?.characters" :key="uid" class="check"><input v-model="carryActors" type="checkbox" :value="String(uid)">{{ finale?.character_names?.[uid] || uid }} <button @click="download(true, String(uid))">{{ c('导出角色', 'Export character') }}</button></label><button :disabled="busy || !carryActors.length" @click="carry">{{ c('创建下一局（保留旧档案）', 'Create next game (keep archive)') }}</button><a v-if="nextGame" :href="`#/play?game=${encodeURIComponent(nextGame)}`">{{ c('进入下一局', 'Open next game') }}</a></details>
    </template>
    <template v-else-if="preparing && !isGm"><p role="status">{{ c('GM 正在准备尾声与结算，本局暂时不能提交行动。', 'The GM is preparing the finale. Actions are temporarily frozen.') }}</p></template>
    <template v-else-if="preparing && isGm">
      <p>{{ c('已冻结本局。现在取消可恢复游玩；正式提交后不能取消。可手写材料，也可选择 AI 起草。', 'The run is frozen. Cancel now to resume play; committed settlement cannot be cancelled. Write materials manually or draft with AI.') }}</p>
      <label>{{ c('公开尾声', 'Public epilogue') }}<textarea v-model="epilogue" maxlength="80000" @input="review = false" /></label>
      <label>{{ c('公开全程团录', 'Public whole-run recap') }}<textarea v-model="recap" maxlength="80000" @input="review = false" /></label>
      <label>{{ c('GM 私有补充（不会给玩家）', 'Private GM notes (not shared)') }}<textarea v-model="notes" maxlength="80000" @input="review = false" /></label>
      <label class="check"><input v-model="consent" type="checkbox">{{ c('AI 将读取整次运行的公开日志并消耗 token。取消不能撤回已发生的用量。', 'AI reads the whole public run and consumes tokens. Cancellation cannot undo usage.') }}</label>
      <div class="finale-actions"><button :disabled="busy || !consent" @click="generate">{{ c('AI 起草尾声与团录', 'Draft finale with AI') }}</button><button v-if="busy && controller" @click="controller.abort()">{{ c('取消生成', 'Cancel generation') }}</button><button :disabled="busy" @click="mutate('cancel')">{{ c('取消结团，继续游玩', 'Cancel finale and resume play') }}</button></div>
      <p v-if="progress" role="status">{{ progress.stage }} · {{ progress.completed }}/{{ progress.total }}<progress :value="progress.completed" :max="Math.max(1, progress.total)" /></p>
      <button data-testid="review-finale" :disabled="busy || !epilogue.trim() || !recap.trim()" @click="saveMaterials">{{ c('保存材料并检查结算', 'Save materials and review settlement') }}</button>
      <div v-if="review" class="finale-review"><p>{{ c('提交将执行规则支持的幕间成长并结束本局。不会自动补发经验、SAN 或金钱。结算结果会永久保存；导出失败可重试。', 'Commit applies supported intermission growth and ends the run. No automatic extra XP, SAN or money. Results are permanent; failed exports can be retried.') }}</p><label class="check"><input v-model="confirmed" type="checkbox">{{ c('已核对公开材料，确认结束本次冒险', 'I reviewed the public materials and confirm the end of this adventure') }}</label><button data-testid="commit-finale" class="primary" :disabled="busy || !confirmed" @click="mutate('commit', { confirmed: true })">{{ c('提交结算并结团', 'Commit settlement and end run') }}</button></div>
    </template>
    <template v-else-if="isGm && state?.ok">
      <details v-if="state?.growth?.supported"><summary>{{ c('技能成长勾选', 'Skill development marks') }} · {{ state.growth.pending.length }}</summary><p>{{ c('仅由已结算的成功技能检定产生；幸运改成的成功不打勾，技能数值在幕间前不变。', 'Marks come from settled successful skill checks; luck-spent checks do not mark. Values stay unchanged until intermission.') }}</p><ul><li v-for="(mark, index) in state.growth.pending" :key="index">{{ mark.actor_uid }} · {{ mark.label }}</li></ul><button :disabled="busy || !state.growth.pending.length || !!state.blockers?.length" @click="intermission">{{ c('结算本次幕间成长', 'Settle intermission growth') }}</button></details>
      <p>{{ c('结束前需处理行动、战斗、检定、休息和待领取奖励。准备阶段不会发放成长或奖励。', 'Resolve actions, combat, checks, rest and pending rewards first. Preparation awards nothing.') }}</p>
      <ul v-if="state?.blockers?.length"><li v-for="problem in state.blockers" :key="problem">{{ problem }}</li></ul>
      <button :disabled="busy || !!state?.blockers?.length" @click="mutate('prepare')">{{ c('准备结束本次冒险', 'Prepare to end this adventure') }}</button>
    </template>
    <p v-else>{{ c('正在读取本局状态…', 'Loading the current run…') }}</p>
    <p v-if="error" role="alert">{{ error }} <button @click="load">{{ c('重试', 'Retry') }}</button></p>
  </section>
</template>

<style scoped>
.run-finale { display: grid; gap: 12px; min-width: 0; padding: 14px; border: 1px solid var(--df-border-soft); border-radius: 8px; } h3, h4, p, pre { margin: 0; overflow-wrap: anywhere; } h3 { font-size: 15px; } h4 { font-size: 13px; } p, li { font-size: 12px; line-height: 1.6; color: var(--df-text-secondary); } label { display: grid; gap: 6px; font-size: 12px; } textarea { width: 100%; min-height: 100px; box-sizing: border-box; resize: vertical; } .check { display: flex; gap: 8px; align-items: flex-start; } .check input { width: auto; flex: 0 0 auto; } .finale-actions { display: flex; gap: 8px; flex-wrap: wrap; } .finale-review { display: grid; gap: 12px; padding: 12px; border: 1px solid var(--df-border-soft); border-radius: 8px; } .public-text, pre { white-space: pre-wrap; } pre { max-height: 240px; overflow: auto; font-size: 11px; } details { min-width: 0; } details[open] > :not(summary) { margin-top: 10px; } progress { display: block; width: 100%; } [role='alert'] { color: var(--df-danger-strong); }
</style>
