<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useLocale } from '@/composables/useLocale'
import { changeStory, generateStory, loadStory, prepareStoryAdventure, storyError as errorMessage, type AiProgress, type RunStoryState, type StoryPlan, type StoryScene } from './api'
import ScriptImportDialog from '@/features/adventures/ScriptImportDialog.vue'
import type { ScriptPreview } from '@/features/adventures/scriptTypes'

const props = defineProps<{ gameKey: string; revision: number | string }>()
const emit = defineEmits<{ changed: [] }>()
const { locale } = useLocale()
const c = (zh: string, en: string) => locale.value === 'zh-CN' ? zh : en
const state = ref<RunStoryState>(), draft = ref<StoryPlan>(), error = ref(''), busy = ref(false)
const consent = ref(false), instructions = ref(''), source = ref('gm'), progress = ref<AiProgress>()
const evidence = ref(''), nextId = ref(''), confirmed = ref(false)
const adventureId = ref(`story_${crypto.randomUUID().replaceAll('-', '').slice(0, 12)}`)
const adventurePreview = ref<ScriptPreview>(), publishedAdventure = ref('')
let controller: AbortController | undefined, generation = 0
const current = computed(() => state.value?.story.plan?.scenes.find(s => s.id === state.value?.story.current_id))
const readonly = computed(() => state.value?.finale?.status !== 'playing')
async function load() {
  const request = ++generation
  try { const result = await loadStory(props.gameKey); if (request === generation) { state.value = result; if (!result.ok) error.value = result.error || 'Unavailable' } }
  catch (e) { if (request === generation) error.value = errorMessage(e) }
}
function scene(): StoryScene { return { id: `scene_${crypto.randomUUID().replaceAll('-', '')}`, title: '', kind: 'investigation', objective: '', description: '', public: true, exit: '', next_ids: [], hints: [] } }
function edit() {
  source.value = 'gm'
  if (state.value?.story.plan) draft.value = JSON.parse(JSON.stringify(state.value.story.plan))
  else { const first = scene(); draft.value = { format_version: 1, theme: '', party_goal: '', mode: 'guided', npc_policy: 'open', core_npcs: [], start: first.id, scenes: [first] } }
}
function addScene() {
  if (!draft.value || draft.value.scenes.length >= 24) return
  const next = scene(), previous = draft.value.scenes.at(-1)
  if (previous) previous.next_ids.push(next.id)
  draft.value.scenes.push(next)
}
function removeScene(id: string) {
  if (!draft.value || draft.value.scenes.length < 2 || draft.value.start === id) return
  draft.value.scenes = draft.value.scenes.filter(s => s.id !== id)
  draft.value.scenes.forEach(s => { s.next_ids = s.next_ids.filter(i => i !== id) })
}
async function mutate(action: string, body: object) {
  busy.value = true; error.value = ''
  const key = props.gameKey; generation++
  try { const result = await changeStory(key, action, { ...body, run_id: state.value?.run_id }); if (key !== props.gameKey) return false; if (!result.ok) throw new Error(result.error || 'Operation failed'); generation++; state.value = result; emit('changed'); return true }
  catch (e) { if (key === props.gameKey) error.value = errorMessage(e); return false }
  finally { busy.value = false }
}
async function adopt() { if (await mutate('plan', { plan: draft.value, revision: state.value?.story.revision || 0, source: source.value })) draft.value = undefined }
async function advance() {
  if (!state.value || !confirmed.value) return
  await mutate('advance', { confirmed: true, candidate: { format_version: 1, run_id: state.value.run_id, revision: state.value.story.revision,
    from_id: state.value.story.current_id, to_id: nextId.value, evidence_rounds: evidence.value.split(/[,，\s]+/).filter(Boolean).map(Number) } })
  confirmed.value = false
}
async function generate() {
  if (!consent.value || busy.value) return
  const key = props.gameKey; controller = new AbortController(); busy.value = true; error.value = ''
  try { const result = await generateStory(key, 'plan', { run_id: state.value?.run_id, token_consent: true, instructions: instructions.value }, controller.signal, p => { progress.value = p }); if (key === props.gameKey) { draft.value = result.plan; source.value = 'ai_original' } }
  catch (e) { if (!controller.signal.aborted) error.value = errorMessage(e) }
  finally { busy.value = false; progress.value = undefined }
}
async function prepareAdventure() {
  if (busy.value || !state.value?.story.plan) return
  const key = props.gameKey
  const revision = state.value.story.revision
  busy.value = true; error.value = ''; publishedAdventure.value = ''
  try {
    const result = await prepareStoryAdventure(key, { run_id: state.value.run_id, revision, directory_id: adventureId.value })
    if (key !== props.gameKey) return
    if (!result.ok) throw new Error(result.error || c('无法整理冒险草稿', 'Could not prepare Adventure draft'))
    adventurePreview.value = result
  } catch (e) { if (key === props.gameKey) error.value = errorMessage(e) }
  finally { busy.value = false }
}
watch(() => [props.gameKey, props.revision], () => { void load() }, { immediate: true })
watch(() => props.gameKey, () => { controller?.abort(); draft.value = undefined; adventurePreview.value = undefined; publishedAdventure.value = '' })
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <details class="run-story-panel" data-testid="run-story-panel">
    <summary>{{ c('剧情计划', 'Story plan') }} <small>{{ current?.title || c('尚未创建 · 自由沙盒', 'No plan · sandbox') }}</small></summary>
    <div class="story-body">
      <p v-if="state?.adventure_bound">{{ c('本局使用冒险包的节点与目标，请在冒险面板推进。', 'This game uses its adventure runtime. Advance nodes in the adventure panel.') }}</p>
      <template v-else>
        <div v-if="current" class="story-current"><strong>{{ current.title }}</strong><p>{{ current.objective }}</p><p>{{ c('转场条件：', 'Exit condition: ') }}{{ state?.story.exit }}</p><small>{{ c('来源：', 'Source: ') }}{{ state?.story.source === 'ai_original' ? c('本局 AI 原创', 'AI original for this run') : 'GM' }}</small></div>
        <p v-if="state?.story.stall_hint" class="notice">{{ c('停滞提示（GM 可选择采用）：', 'Stall hint (GM decides): ') }}{{ state.story.stall_hint }}</p>
        <p v-if="!readonly">{{ c('可不设固定计划继续自由游玩。采用计划只影响本局，不改写世界资料。', 'Playing without a fixed plan is supported. Adoption affects this run only.') }}</p>
        <div v-if="!readonly" class="story-actions"><button data-testid="edit-plan" :disabled="busy" @click="edit">{{ c('新建 / 编辑计划', 'Create / edit plan') }}</button><button v-if="draft" :disabled="busy" @click="draft = undefined">{{ c('收起草稿', 'Close draft') }}</button></div>
        <form v-if="draft && !readonly" class="story-editor" @submit.prevent="adopt">
          <label>{{ c('主题', 'Theme') }}<input v-model="draft.theme" maxlength="240" required></label>
          <label>{{ c('团队目标', 'Party goal') }}<textarea v-model="draft.party_goal" maxlength="400" required /></label>
          <div class="story-columns"><label>{{ c('玩法', 'Mode') }}<select v-model="draft.mode"><option value="guided">{{ c('引导剧情', 'Guided') }}</option><option value="sandbox">{{ c('自由沙盒', 'Sandbox') }}</option></select></label><label>{{ c('人物策略', 'NPC policy') }}<select v-model="draft.npc_policy"><option value="open">{{ c('宽松：允许新增人物', 'Open: allow new NPCs') }}</option><option value="strict">{{ c('严格：新增人物状态须先采用', 'Strict: adopt new NPC state first') }}</option></select></label></div>
          <fieldset v-if="state?.available_npcs?.length"><legend>{{ c('核心人物（已有人物）', 'Core NPCs (existing identities)') }}</legend><label v-for="npc in state.available_npcs" :key="npc.id" class="check"><input v-model="draft.core_npcs" type="checkbox" :value="npc.id">{{ npc.name }}</label></fieldset>
          <details v-for="(item, index) in draft.scenes" :key="item.id" :open="index === 0" class="story-scene">
            <summary>{{ index + 1 }} · {{ item.title || c('新场景', 'New scene') }}</summary>
            <label>{{ c('场景', 'Scene') }}<input v-model="item.title" maxlength="160" required></label>
            <label>{{ c('类型', 'Kind') }}<select v-model="item.kind"><option v-for="kind in ['transition', 'investigation', 'social', 'combat', 'exploration', 'finale']" :key="kind" :value="kind">{{ c(({ transition: '过渡', investigation: '调查', social: '交涉', combat: '战斗', exploration: '探索', finale: '结局' } as Record<string, string>)[kind] || kind, kind) }}</option></select></label>
            <label>{{ c('当前目标', 'Objective') }}<input v-model="item.objective" maxlength="240" required></label>
            <label>{{ c('场景描述', 'Description') }}<textarea v-model="item.description" maxlength="800" /></label>
            <label class="check"><input v-model="item.public" type="checkbox">{{ c('到达后向玩家公开目标', 'Reveal objective to players on arrival') }}</label>
            <label>{{ c('转场条件（由 GM 确认）', 'Exit condition (GM confirms)') }}<textarea v-model="item.exit" maxlength="500" required /></label>
            <label>{{ c('停滞时的替代入口 / 提示', 'Alternative route / stall hint') }}<input :value="item.hints[0] || ''" maxlength="500" @input="item.hints = [($event.target as HTMLInputElement).value]"></label>
            <fieldset><legend>{{ c('可前往的场景', 'Possible successors') }}</legend><label v-for="target in draft.scenes.filter(s => s.id !== item.id)" :key="target.id" class="check"><input v-model="item.next_ids" type="checkbox" :value="target.id">{{ target.title || c('未命名', 'Untitled') }}</label></fieldset>
            <button v-if="index > 0" type="button" @click="removeScene(item.id)">{{ c('删除场景', 'Remove scene') }}</button>
          </details>
          <div class="story-actions"><button type="button" @click="addScene">{{ c('添加场景', 'Add scene') }}</button><button class="primary" type="submit" :disabled="busy">{{ c('采用本局计划', 'Adopt for this run') }}</button></div>
          <small>{{ c('重新采用会从草稿的起始场景开始；已有回合与权威结果保留。', 'Re-adoption starts at the draft’s first scene; existing rounds and outcomes remain.') }}</small>
        </form>
        <details v-if="!readonly" class="story-ai"><summary>{{ c('AI 起草计划', 'Draft with AI') }}</summary><label>{{ c('补充要求', 'Instructions') }}<textarea v-model="instructions" maxlength="2000" /></label><label class="check"><input v-model="consent" type="checkbox">{{ c('生成会消耗模型 token；取消不能撤回已发生的用量。草稿须另行采用。', 'Generation consumes model tokens. Cancellation cannot undo usage. Review and adopt the draft separately.') }}</label><div class="story-actions"><button :disabled="!consent || busy" @click="generate">{{ c('生成草稿', 'Generate draft') }}</button><button v-if="busy && controller" @click="controller.abort()">{{ c('取消生成', 'Cancel generation') }}</button></div><p v-if="progress" role="status">{{ c('生成阶段：', 'Stage: ') }}{{ progress.stage }} · {{ progress.completed }}/{{ progress.total }}<progress :value="progress.completed" :max="Math.max(1, progress.total)" /></p></details>
        <details v-if="current && !readonly" class="story-transition"><summary>{{ c('确认剧情推进', 'Confirm transition') }}</summary><p>{{ state?.story.exit }}</p><label>{{ c('下一场景', 'Next scene') }}<select v-model="nextId"><option value="">—</option><option v-for="next in state?.story.possible_next_nodes" :key="next.id" :value="next.id">{{ next.name }}</option></select></label><label>{{ c('依据回合（逗号分隔）', 'Evidence rounds (comma separated)') }}<input v-model="evidence" inputmode="numeric"></label><label class="check"><input v-model="confirmed" type="checkbox">{{ c('我已核对回合事实满足转场条件', 'I verified that committed facts meet the exit condition') }}</label><button :disabled="busy || !confirmed || !nextId || !evidence" @click="advance">{{ c('提交推进', 'Commit transition') }}</button></details>
      </template>
      <details v-if="state?.story.plan && !state.adventure_bound" class="story-editor">
        <summary>{{ c('整理为冒险包', 'Create reusable Adventure') }}</summary>
        <p>{{ c('把已采用的计划复制为独立草稿，再编辑、审阅和发布。场景默认仅 GM 可见，保留转场条件和提示；不复制本局进度、人物状态或聊天记录。', 'Copy the adopted plan to an independent draft for editing, review and publication. Scenes start GM-only with exit conditions and hints. Live progress, characters and chat are excluded.') }}</p>
        <label>{{ c('冒险标识', 'Adventure identity') }}<input v-model="adventureId" data-testid="story-adventure-id" pattern="[a-z0-9][a-z0-9_.-]*" maxlength="80"></label>
        <button data-testid="story-adventure-prepare" :disabled="busy || !/^[a-z0-9][a-z0-9_.-]*$/.test(adventureId)" @click="prepareAdventure">{{ c('整理并审阅草稿', 'Prepare and review draft') }}</button>
        <p v-if="publishedAdventure" role="status">{{ c('已保存到冒险库：', 'Saved to Adventures: ') }}{{ publishedAdventure }}</p>
      </details>
      <details v-if="state?.story.plan"><summary>{{ c('GM 诊断', 'GM diagnostics') }}</summary><p>{{ c('计划版本：', 'Plan revision: ') }}{{ state.story.revision }}</p><p v-for="(warning, index) in state.story.warnings" :key="index" role="alert">{{ warning }}</p><pre v-if="state.story.candidate">{{ state.story.candidate }}</pre><p>{{ c('模型提出的推进仅供审阅，不会自动修改进度。', 'Model proposals are advisory and cannot commit progress.') }}</p></details>
      <details v-if="state?.context_diagnostics?.text"><summary>{{ c('当前剧情上下文', 'Current story context') }}</summary><p>{{ c('剧情块上限：', 'Story-block limit: ') }}{{ state.context_diagnostics.max_chars }} · {{ c('当前字符数：', 'Current characters: ') }}{{ state.context_diagnostics.used_chars }}</p><p>{{ c('实际额度还受模型窗口限制。这里只展示剧情投影，不包含完整 GM 提示词。', 'The model context window may reduce this budget. This view contains only the story projection.') }}</p><pre>{{ state.context_diagnostics.text }}</pre></details>
      <p v-if="error" role="alert">{{ error }} <button @click="load">{{ c('重试', 'Retry') }}</button></p>
    </div>
    <ScriptImportDialog v-if="adventurePreview" :initial-preview="adventurePreview" @close="adventurePreview = undefined" @published="publishedAdventure = $event; adventurePreview = undefined" />
  </details>
</template>

<style scoped>
.run-story-panel { border: 1px solid var(--df-border-soft); border-radius: 8px; padding: 12px; min-width: 0; } summary { cursor: pointer; color: var(--df-text); } summary small { display: block; color: var(--df-text-secondary); margin-top: 4px; } .story-body, .story-editor, .story-scene, .story-ai, .story-transition { display: grid; gap: 12px; } .story-body { margin-top: 14px; } details:not([open]) { display: block; } label { display: grid; gap: 6px; font-size: 12px; min-width: 0; } .check { display: flex; align-items: flex-start; gap: 8px; } .check input { width: auto; flex: 0 0 auto; } input, select, textarea { width: 100%; box-sizing: border-box; } textarea { min-height: 64px; resize: vertical; } p, pre { margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; } p, small { font-size: 12px; color: var(--df-text-secondary); } .story-actions { display: flex; flex-wrap: wrap; gap: 8px; } .story-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; } fieldset { min-width: 0; border: 1px solid var(--df-border-soft); display: grid; gap: 8px; } legend { font-size: 12px; } progress { display: block; width: 100%; margin-top: 8px; } [role='alert'] { color: var(--df-danger-strong); } @media (max-width: 480px) { .story-columns { grid-template-columns: 1fr; } }
</style>
