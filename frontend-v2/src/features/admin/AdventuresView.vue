<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, apiBlob, errorMessage } from '@/api/client'
import type {
  AdventureDetailResponse, AdventureSummary, AdventuresResponse, WorldListResponse, WorldSummary,
} from '@/api/types'
import { useConfirm } from '@/composables/useConfirm'
import { useLocale } from '@/composables/useLocale'
import { useToast } from '@/composables/useToast'
import Modal from '@/components/ui/Modal.vue'

const { locale, t } = useLocale()
const { confirm } = useConfirm()
const toast = useToast()
const items = ref<AdventureSummary[]>([])
const worlds = ref<WorldSummary[]>([])
const error = ref('')
const busy = ref(false)
const importInput = ref<HTMLInputElement | null>(null)
const copySource = ref<AdventureSummary | null>(null)
const copyForm = ref({ directory_id: '', adventure_id: '', name: '', summary: '', version: '1.0.0' })
const editing = ref<AdventureSummary | null>(null)
const filesJson = ref('')
const editingFiles = ref<Record<string, unknown>>({})
const createOpen = ref(false)
const createSource = ref<'manual' | 'ai'>('manual')
const createStep = ref<1 | 2>(1)
const aiBusy = ref(false)
const aiPrompt = ref('')
const pendingAiDraft = ref<any | null>(null)
const editingCreation = ref(false)
const advancedOpen = ref(false)
const editorPanel = ref<'overview' | 'flow' | 'encounters' | 'preview' | 'advanced'>('overview')
const editorAiPrompt = ref('')
const editorAiBusy = ref(false)
const createForm = ref({ directory_id: '', adventure_id: '', name: '', summary: '', version: '1.0.0', world_policy: 'portable', recommended_world_id: '', estimated_minutes: 60 })
const editorForm = ref({ name: '', summary: '', version: '1.0.0', world_policy: 'portable', recommended_world_id: '', estimated_minutes: 60 })
type EditorStep = { id: string; chapter_id: string; scene_ref: string; requires: string; encounter_preset_id: string; title: string; narration: string; objective: string; hint: string }
type EditorChoice = { id: string; step_id: string; next_step_id: string; label: string; description: string }
type EditorChapter = { id: string; name: string }
type EditorScene = { ref: string; name: string }
type EditorAttack = { id: string; damage: string; attack_bonus: number }
type EditorEnemy = { id: string; profile_id: string; hp: number; armor_class: number; attacks: EditorAttack[] }
type EditorEncounter = { id: string; name: string; difficulty: string; description: string; catalog_path: string; enemies: EditorEnemy[] }
const editorSteps = ref<EditorStep[]>([])
const editorChoices = ref<EditorChoice[]>([])
const editorChapters = ref<EditorChapter[]>([])
const editorScenes = ref<EditorScene[]>([])
const editorEncounters = ref<EditorEncounter[]>([])
const editorStartStepId = ref('')

const editorGraphIssues = computed(() => {
  const stepIds = new Set(editorSteps.value.map(step => step.id))
  const chapterIds = new Set(editorChapters.value.map(chapter => chapter.id))
  const encounterIds = new Set(editorEncounters.value.map(encounter => encounter.id))
  const issues: string[] = []
  if (!editorStartStepId.value || !stepIds.has(editorStartStepId.value)) {
    issues.push(String(locale.value).startsWith('zh') ? '未选择有效的冒险起点。' : 'Choose a valid adventure start step.')
  }
  editorSteps.value.forEach(step => {
    if (!chapterIds.has(step.chapter_id)) issues.push(`步骤「${step.title || step.id}」没有有效章节。`)
    if (step.encounter_preset_id && !encounterIds.has(step.encounter_preset_id)) issues.push(`步骤「${step.title || step.id}」引用了不存在的遭遇。`)
  })
  const incoming = new Set<string>()
  editorChoices.value.forEach(choice => {
    if (!stepIds.has(choice.step_id)) issues.push(`选项「${choice.label || choice.id}」没有有效来源步骤。`)
    if (choice.next_step_id) {
      if (!stepIds.has(choice.next_step_id)) issues.push(`选项「${choice.label || choice.id}」跳转目标不存在。`)
      else incoming.add(choice.next_step_id)
    }
  })
  editorSteps.value.forEach(step => {
    if (step.id !== editorStartStepId.value && !incoming.has(step.id)) issues.push(`步骤「${step.title || step.id}」从起点不可达。`)
  })
  return [...new Set(issues)]
})

const editorFlowPreview = computed(() => editorSteps.value.map((step, index) => ({
  step,
  index,
  outgoing: editorChoices.value
    .filter(choice => choice.step_id === step.id)
    .map(choice => ({ label: choice.label || '继续', target: editorSteps.value.find(item => item.id === choice.next_step_id)?.title || (choice.next_step_id ? choice.next_step_id : '结局') })),
})))

const builtinCount = computed(() => items.value.filter(item => !item.custom).length)
const customCount = computed(() => items.value.filter(item => item.custom).length)
const boundCount = computed(() => items.value.filter(item => Number(item.in_use || 0) > 0).length)
const editingFileGroups = computed(() => {
  const files = Object.keys(editingFiles.value)
  return [
    { label: '身份与元数据', paths: files.filter(path => path === 'manifest.json' || path === 'adventure.json') },
    { label: '剧情内容', paths: files.filter(path => path.startsWith('content/')) },
    { label: '本地化文本', paths: files.filter(path => path.startsWith('locales/')) },
  ].filter(group => group.paths.length)
})

async function load() {
  error.value = ''
  try {
    const [result, worldResult] = await Promise.all([
      api<AdventuresResponse>(`/adventures?rule_id=dnd2024_srd&language=${encodeURIComponent(locale.value)}`),
      api<WorldListResponse>('/worlds'),
    ])
    items.value = result.adventures || []
    worlds.value = worldResult.worlds || []
  } catch (cause: unknown) {
    error.value = errorMessage(cause)
  }
}

onMounted(load)

function safeStem(value: string) {
  return value.toLowerCase().replace(/^[^a-z0-9]+/, '').replace(/[^a-z0-9_.-]+/g, '_').slice(0, 48) || 'adventure'
}

function openCopy(item: AdventureSummary) {
  const stem = `custom_${safeStem(item.directory_id || item.adventure_id.split(':').pop() || '')}`
  copySource.value = item
  copyForm.value = {
    directory_id: stem,
    adventure_id: `user:${stem}`,
    name: `${item.name} · ${t('adventureCopySuffix')}`,
    summary: item.summary || '',
    version: '1.0.0',
  }
}

function openCreate(source: 'manual' | 'ai' = 'manual') {
  createForm.value = { directory_id: '', adventure_id: '', name: '', summary: '', version: '1.0.0', world_policy: 'portable', recommended_world_id: '', estimated_minutes: 60 }
  createSource.value = source
  createStep.value = 1
  aiPrompt.value = ''
  pendingAiDraft.value = null
  createOpen.value = true
}

function openAiDraft() {
  openCreate('ai')
}

type AiDraftEnemy = { profile_id?: string; hp?: number; armor_class?: number; attacks?: Array<{ id?: string; damage?: string; attack_bonus?: number }> }
type AiDraftEncounter = { name?: string; difficulty?: string; description?: string; stepIndex?: number | null; enemies?: AiDraftEnemy[] }
type AiDraft = { name?: string; summary?: string; encounters?: AiDraftEncounter[]; chapters?: Array<{ name?: string; steps?: Array<{ title?: string; narration?: string; objective?: string; hint?: string; choices?: Array<{ label?: string; description?: string; nextStepIndex?: number | null }> }> }> }
type AiOverviewDraft = { name?: string; summary?: string; world_policy?: string; recommended_world_id?: string; estimated_minutes?: number }
type AiEditorDraft = AiDraft & AiOverviewDraft
const aiDraftCounts = computed(() => {
  const chapters = pendingAiDraft.value?.chapters || []
  return {
    chapters: chapters.length,
    steps: chapters.reduce((total: number, chapter: { steps?: unknown[] }) => total + (chapter.steps?.length || 0), 0),
    encounters: Array.isArray(pendingAiDraft.value?.encounters) ? pendingAiDraft.value.encounters.length : 0,
  }
})

function normalizeAiEncounters(encounters: AiDraftEncounter[]) {
  const defaultCatalogPath = editorEncounters.value[0]?.catalog_path || 'content/encounters/adventure_encounters.json'
  return encounters.map((encounter, encounterIndex) => ({
    id: `encounter_${encounterIndex + 1}`,
    name: String(encounter.name || `遭遇 ${encounterIndex + 1}`),
    difficulty: ['story', 'standard', 'challenging', 'lethal'].includes(String(encounter.difficulty)) ? String(encounter.difficulty) : 'standard',
    description: String(encounter.description || ''),
    catalog_path: defaultCatalogPath,
    enemies: (Array.isArray(encounter.enemies) ? encounter.enemies : []).map((enemy, enemyIndex) => ({
      id: `enemy_${encounterIndex + 1}_${enemyIndex + 1}`,
      profile_id: String(enemy.profile_id || 'custom_enemy'),
      hp: Math.max(1, Math.min(10000, Number(enemy.hp || 10))),
      armor_class: Math.max(1, Math.min(40, Number(enemy.armor_class || 12))),
      attacks: (Array.isArray(enemy.attacks) && enemy.attacks.length ? enemy.attacks : [{ id: 'attack', damage: '1d6+2', attack_bonus: 4 }]).map((attack, attackIndex) => ({
        id: String(attack.id || `attack_${attackIndex + 1}`),
        damage: String(attack.damage || '1d6+2'),
        attack_bonus: Math.max(-20, Math.min(20, Number(attack.attack_bonus || 0))),
      })),
    })),
  }))
}

function applyAiEncountersDraft(encounters: AiDraftEncounter[]) {
  editorEncounters.value = normalizeAiEncounters(encounters)
  editorSteps.value.forEach(step => { step.encounter_preset_id = '' })
  editorEncounters.value.forEach((encounter, encounterIndex) => {
    const source = encounters[encounterIndex]
    const stepIndex = source && typeof source.stepIndex === 'number' ? source.stepIndex : -1
    if (stepIndex >= 0 && stepIndex < editorSteps.value.length) editorSteps.value[stepIndex].encounter_preset_id = encounter.id
  })
}

function applyAiFlowDraft(chapters: NonNullable<AiDraft['chapters']>) {
  const scenes = editorScenes.value
  editorChapters.value = chapters.map((chapter, chapterIndex) => ({ id: `chapter_${chapterIndex + 1}`, name: String(chapter.name || `第 ${chapterIndex + 1} 章`) }))
  editorSteps.value = []
  editorChoices.value = []
  const stepIds: string[] = []
  chapters.forEach((chapter, chapterIndex) => (chapter.steps || []).forEach((step, stepIndex) => {
    const id = `step_${chapterIndex + 1}_${stepIndex + 1}`
    stepIds.push(id)
    editorSteps.value.push({ id, chapter_id: `chapter_${chapterIndex + 1}`, scene_ref: scenes[editorSteps.value.length]?.ref || scenes[0]?.ref || '', requires: 'none', encounter_preset_id: '', title: String(step.title || '未命名步骤'), narration: String(step.narration || ''), objective: String(step.objective || ''), hint: String(step.hint || '') })
  }))
  let choiceIndex = 0
  let stepCursor = 0
  chapters.forEach(chapter => (chapter.steps || []).forEach(step => {
    const currentStep = stepIds[stepCursor] || stepIds[0]
    stepCursor += 1
    ;(step.choices || []).forEach(choice => {
      const target = typeof choice.nextStepIndex === 'number' ? stepIds[choice.nextStepIndex] || '' : ''
      editorChoices.value.push({ id: `choice_${++choiceIndex}`, step_id: currentStep, next_step_id: target, label: String(choice.label || '新选项'), description: String(choice.description || '') })
    })
  }))
  // Keep the graph playable even when the model omits links.
  const incoming = new Set(editorChoices.value.map(choice => choice.next_step_id).filter(Boolean))
  stepIds.forEach((stepId, index) => {
    if (index > 0 && !incoming.has(stepId)) {
      editorChoices.value.push(makeChoice(stepIds[index - 1], stepId))
      incoming.add(stepId)
    }
  })
  editorStartStepId.value = editorSteps.value[0]?.id || ''
}

function applyAiDraft(draft: AiDraft) {
  const chapters = Array.isArray(draft.chapters) ? draft.chapters : []
  editorForm.value.name = String(draft.name || editorForm.value.name)
  editorForm.value.summary = String(draft.summary || editorForm.value.summary)
  applyAiFlowDraft(chapters)
  applyAiEncountersDraft(Array.isArray(draft.encounters) ? draft.encounters : [])
}

function applyAiOverviewDraft(draft: AiOverviewDraft) {
  if (draft.name) editorForm.value.name = String(draft.name)
  if (draft.summary) editorForm.value.summary = String(draft.summary)
  if (['portable', 'agnostic', 'fixed'].includes(String(draft.world_policy))) editorForm.value.world_policy = String(draft.world_policy)
  if (draft.recommended_world_id !== undefined) editorForm.value.recommended_world_id = String(draft.recommended_world_id || '')
  if (draft.estimated_minutes !== undefined) editorForm.value.estimated_minutes = Math.max(1, Math.min(999, Number(draft.estimated_minutes) || 60))
}

function editorAiPanelTitle() {
  const zh = String(locale.value).startsWith('zh')
  if (editorPanel.value === 'overview') return zh ? '生成概览草稿' : 'Generate overview draft'
  if (editorPanel.value === 'flow') return zh ? '生成流程草稿' : 'Generate flow draft'
  return zh ? '生成遭遇草稿' : 'Generate encounter draft'
}

function editorAiPlaceholder() {
  const zh = String(locale.value).startsWith('zh')
  if (editorPanel.value === 'overview') return zh ? '例如：一场 60 分钟、适合新手的森林调查冒险。' : 'e.g. A 60-minute beginner adventure investigating a forest.'
  if (editorPanel.value === 'flow') return zh ? '例如：三章结构，包含一个分支和一个有明确目标的结局。' : 'e.g. Three chapters, one meaningful branch, and a clear ending goal.'
  return zh ? '例如：第二章的哥布林伏击，2 只普通哥布林，带弯刀攻击。' : 'e.g. A chapter-two goblin ambush with two standard goblins using scimitars.'
}

async function generateEditorPanelDraft() {
  const promptText = editorAiPrompt.value.trim()
  if (!promptText || editorAiBusy.value || !editing.value) return
  const targetPanel = editorPanel.value
  editorAiBusy.value = true
  error.value = ''
  const zh = String(locale.value).startsWith('zh')
  try {
    let shape = ''
    if (targetPanel === 'overview') shape = '{"name":"","summary":"","world_policy":"portable","recommended_world_id":"","estimated_minutes":60}'
    else if (targetPanel === 'flow') shape = '{"chapters":[{"name":"","steps":[{"title":"","narration":"","objective":"","hint":"","choices":[{"label":"","description":"","nextStepIndex":null}]}]}]}'
    else shape = '{"encounters":[{"name":"","difficulty":"standard","description":"","stepIndex":null,"enemies":[{"profile_id":"goblin","hp":7,"armor_class":12,"attacks":[{"id":"scimitar","damage":"1d6+2","attack_bonus":4}]}]}]}'
    const result = await api<{ ok: boolean; text?: string; error?: string }>('/generate-text', {
      method: 'POST',
      body: JSON.stringify({ language: locale.value, prompt: `${zh ? '只生成当前编辑器分区的 JSON 草稿。' : 'Generate JSON for the current editor section only.'}\n用户需求：${promptText}\n格式：${shape}\n不要 Markdown、解释或代码围栏。`, system_hint: zh ? '你是冒险包编辑助手，只输出合法 JSON。' : 'You are an adventure package editor. Output valid JSON only.' }),
    })
    if (!result.ok || !result.text) throw new Error(result.error || (zh ? 'AI 生成失败' : 'AI generation failed'))
    const raw = result.text.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '')
    const draft = JSON.parse(raw) as AiEditorDraft
    const replacingExisting = (targetPanel === 'flow' && editorSteps.value.length > 0)
      || (targetPanel === 'encounters' && editorEncounters.value.length > 0)
    if (replacingExisting) {
      const accepted = await confirm({
        title: zh ? '替换当前分区草稿？' : 'Replace this section draft?',
        content: zh ? 'AI 结果会替换当前分区尚未保存的内容；其它分区不会改变。是否继续？' : 'The AI result will replace unsaved content in this section only. Other sections are unchanged. Continue?',
        positiveText: zh ? '继续生成' : 'Continue',
        type: 'warning',
      })
      if (!accepted) return
    }
    if (targetPanel === 'overview') applyAiOverviewDraft(draft)
    else if (targetPanel === 'flow') {
      const chapters = Array.isArray(draft.chapters) ? draft.chapters : []
      if (!chapters.length) throw new Error(zh ? 'AI 没有返回流程章节' : 'AI returned no flow chapters')
      applyAiFlowDraft(chapters)
    } else {
      const encounters = Array.isArray(draft.encounters) ? draft.encounters : []
      if (!encounters.length) throw new Error(zh ? 'AI 没有返回遭遇' : 'AI returned no encounters')
      applyAiEncountersDraft(encounters)
    }
    editorAiPrompt.value = ''
    toast.success(zh ? '草稿已填入当前分区，请检查后保存' : 'Draft inserted into this section. Review before saving.')
  } catch (cause: unknown) {
    error.value = cause instanceof SyntaxError ? (zh ? 'AI 返回的 JSON 无效' : 'AI returned invalid JSON') : errorMessage(cause)
  } finally {
    editorAiBusy.value = false
  }
}

function worldLabel(world: WorldSummary) {
  return String(world.name || world.world_name || world.id || world.world_id || '')
}

function worldId(world: WorldSummary) {
  return String(world.id || world.world_id || '')
}

async function generateDraft() {
  if (!aiPrompt.value.trim()) return
  aiBusy.value = true
  error.value = ''
  try {
    const result = await api<{ ok: boolean; text?: string; error?: string }>('/generate-text', {
      method: 'POST',
      body: JSON.stringify({
        language: locale.value,
        prompt: `为一个 TRPG 冒险包起草剧情结构。用户需求：${aiPrompt.value.trim()}\n只输出 JSON，不要 Markdown，格式必须是：{"name":"","summary":"","chapters":[{"name":"","steps":[{"title":"","narration":"","objective":"","hint":"","choices":[{"label":"","description":"","nextStepIndex":null}]}]}],"encounters":[{"name":"","difficulty":"standard","description":"","stepIndex":null,"enemies":[{"profile_id":"goblin","hp":7,"armor_class":12,"attacks":[{"id":"scimitar","damage":"1d6+2","attack_bonus":4}]}]}]}。encounters 是可选的结构化战斗配置；stepIndex 指向 chapters 展平后的步骤序号，从 0 开始。不要生成超出普通 D&D 范围的数值。`,
        system_hint: '你是冒险设计助手。只输出符合用户要求的 JSON，不要解释，不要代码围栏。',
      }),
    })
    if (!result.ok || !result.text) throw new Error(result.error || t('aiDraftFailed'))
    const raw = result.text.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '')
    const draft = JSON.parse(raw) as AiDraft
    const chapters = Array.isArray(draft.chapters) && draft.chapters.length ? draft.chapters : []
    if (!chapters.length) throw new Error(t('aiDraftInvalid'))
    createForm.value.name = String(draft.name || createForm.value.name)
    createForm.value.summary = String(draft.summary || createForm.value.summary)
    pendingAiDraft.value = draft
    createStep.value = 2
    toast.success(t('aiDraftReadyCreate'))
  } catch (cause: unknown) {
    error.value = cause instanceof SyntaxError ? t('aiDraftInvalid') : errorMessage(cause)
  } finally {
    aiBusy.value = false
  }
}

async function createPackage() {
  busy.value = true
  error.value = ''
  try {
    if (!createForm.value.directory_id.trim()) {
      createForm.value.directory_id = `adventure_${Date.now().toString(36)}`
    }
    if (!createForm.value.adventure_id.trim()) {
      createForm.value.adventure_id = `user:${createForm.value.directory_id}`
    }
    const result = await api<{ adventure_id: string }>('/adventures', {
      method: 'POST',
      body: JSON.stringify({ ...createForm.value, language: locale.value }),
    })
    toast.success(t('adventureCreated'))
    createOpen.value = false
    await load()
    const created = items.value.find(item => item.adventure_id === result.adventure_id)
    if (created) {
      const generated = pendingAiDraft.value
      await openEditor(created, Boolean(generated))
      if (pendingAiDraft.value) {
        const draft = pendingAiDraft.value
        pendingAiDraft.value = null
        applyAiDraft(draft)
      }
    }
  } catch (cause: unknown) {
    error.value = errorMessage(cause)
  } finally {
    busy.value = false
  }
}

async function copyPackage() {
  if (!copySource.value) return
  busy.value = true
  error.value = ''
  try {
    await api(`/adventures/${encodeURIComponent(copySource.value.adventure_id)}/copy`, {
      method: 'POST',
      body: JSON.stringify({ ...copyForm.value, locale: locale.value }),
    })
    toast.success(t('adventureCopied'))
    copySource.value = null
    await load()
  } catch (cause: unknown) {
    error.value = errorMessage(cause)
  } finally {
    busy.value = false
  }
}

async function openEditor(item: AdventureSummary, asCreationStep = false) {
  error.value = ''
  editorAiPrompt.value = ''
  editorAiBusy.value = false
  try {
    const result = await api<AdventureDetailResponse>(
      `/adventures/${encodeURIComponent(item.adventure_id)}?language=${encodeURIComponent(locale.value)}`,
    )
    editing.value = item
    editingCreation.value = asCreationStep
    editingFiles.value = result.adventure.files
    filesJson.value = JSON.stringify(result.adventure.files, null, 2)
    advancedOpen.value = false
    editorPanel.value = 'overview'
    hydrateStructuredEditor()
  } catch (cause: unknown) {
    error.value = errorMessage(cause)
  }
}

function closeEditor() {
  editing.value = null
  editingCreation.value = false
}

async function cancelEditor() {
  const draft = editingCreation.value ? editing.value : null
  closeEditor()
  if (!draft) return
  try {
    await api(`/adventures/${encodeURIComponent(draft.adventure_id)}`, { method: 'DELETE' })
    await load()
  } catch (cause: unknown) {
    error.value = errorMessage(cause)
  }
}

function hydrateStructuredEditor() {
  const files = editingFiles.value
  const manifest = (files['manifest.json'] || {}) as Record<string, any>
  const adventure = (files['adventure.json'] || {}) as Record<string, any>
  const localePath = `locales/${locale.value}/adventure.json`
  const localeFile = (files[localePath] || files['locales/zh-CN/adventure.json'] || {}) as Record<string, any>
  const tutorial = (localeFile.fields?.tutorial || {}) as Record<string, any>
  editorForm.value = {
    name: String(tutorial.name || adventure.name || ''),
    summary: String(tutorial.summary || adventure.summary || ''),
    version: String(manifest.version || '1.0.0'),
    world_policy: String(manifest.world_policy || 'portable'),
    recommended_world_id: String(manifest.recommended_world_id || adventure.recommended_world_id || ''),
    estimated_minutes: Number(adventure.estimated_minutes || 60),
  }
  const stepTexts = (tutorial.steps || {}) as Record<string, any>
  const chapterTexts = (tutorial.chapters || {}) as Record<string, any>
  editorChapters.value = (Array.isArray(adventure.chapters) ? adventure.chapters : []).map((chapter: any, index: number) => ({
    id: String(chapter.id || `chapter_${index + 1}`), name: String(chapterTexts[chapter.id]?.name || `第 ${index + 1} 章`),
  }))
  editorScenes.value = Object.entries(files)
    .filter(([path, value]) => path.startsWith('content/') && (value as any)?.kind === 'scene')
    .map(([path, value]) => {
      const scene = value as Record<string, any>
      const sceneId = String(scene.id || path.split('/').pop()?.replace(/\.json$/, '') || '')
      const sceneLocale = (files[`locales/${locale.value}/scenes/${sceneId}.json`] || files[`locales/zh-CN/scenes/${sceneId}.json`] || {}) as Record<string, any>
      return { ref: `scene:${sceneId}`, name: String(sceneLocale.fields?.name || sceneId) }
    })
  editorSteps.value = (Array.isArray(adventure.steps) ? adventure.steps : []).map((step: any) => ({
    id: String(step.id || ''), chapter_id: String(step.chapter_id || ''), scene_ref: String(step.scene_ref || ''),
    requires: String(step.requires || 'none'), encounter_preset_id: String(step.encounter_preset_id || ''),
    title: String(stepTexts[step.id]?.title || '未命名步骤'), narration: String(stepTexts[step.id]?.narration || ''),
    objective: String(stepTexts[step.id]?.objective || ''), hint: String(stepTexts[step.id]?.hint || ''),
  }))
  editorStartStepId.value = String(adventure.start_step_id || editorSteps.value[0]?.id || '')
  const choiceTexts = (tutorial.choices || {}) as Record<string, any>
  editorChoices.value = (Array.isArray(adventure.choices) ? adventure.choices : []).map((choice: any) => ({
    id: String(choice.id || ''), step_id: String(choice.step_id || ''), next_step_id: String(choice.next_step_id || ''),
    label: String(choiceTexts[choice.id]?.label || choice.id || ''), description: String(choiceTexts[choice.id]?.description || ''),
  }))
  editorEncounters.value = Object.entries(files)
    .filter(([path, value]) => path.startsWith('content/') && (value as any)?.kind === 'encounter_catalog')
    .flatMap(([path, value]) => {
      const catalog = value as Record<string, any>
      const catalogId = String(catalog.id || path.split('/').pop()?.replace(/\.json$/, '') || '')
      const localeFile = (files[`locales/${locale.value}/encounters/${catalogId}.json`] || files[`locales/zh-CN/encounters/${catalogId}.json`] || {}) as Record<string, any>
      const labels = (localeFile.fields?.labels?.presets || {}) as Record<string, any>
      return (Array.isArray(catalog.presets) ? catalog.presets : []).map((preset: any) => {
        const id = String(preset.id || '')
        const label = labels[id] as Record<string, any> | undefined
        return {
          id,
          name: String(label?.name || id || '未命名遭遇'),
          difficulty: String(preset.difficulty || 'standard'),
          description: String(label?.description || ''),
          catalog_path: path,
          enemies: (Array.isArray(preset.enemies) ? preset.enemies : []).map((enemy: any, enemyIndex: number) => ({
            id: String(enemy.id || `enemy_${enemyIndex + 1}`),
            profile_id: String(enemy.profile_id || ''),
            hp: Math.max(1, Number(enemy.hp || 1)),
            armor_class: Math.max(1, Number(enemy.armor_class || 10)),
            attacks: (Array.isArray(enemy.attacks) ? enemy.attacks : []).map((attack: any, attackIndex: number) => ({
              id: String(attack.id || `attack_${attackIndex + 1}`),
              damage: String(attack.damage || '1d4'),
              attack_bonus: Number(attack.attack_bonus || 0),
            })),
          })),
        }
      })
    })
}

function syncStructuredEditor() {
  const files = JSON.parse(JSON.stringify(editingFiles.value)) as Record<string, any>
  const manifest = files['manifest.json'] as Record<string, any>
  const adventure = files['adventure.json'] as Record<string, any>
  const localePath = `locales/${locale.value}/adventure.json`
  const localeFile = (files[localePath] || files['locales/zh-CN/adventure.json']) as Record<string, any>
  const tutorial = (localeFile.fields ||= {}).tutorial ||= {}
  manifest.version = editorForm.value.version.trim() || '1.0.0'
  manifest.world_policy = editorForm.value.world_policy
  manifest.recommended_world_id = editorForm.value.recommended_world_id.trim()
  adventure.estimated_minutes = Math.max(1, Number(editorForm.value.estimated_minutes || 60))
  const originalChapters = Array.isArray(adventure.chapters) ? adventure.chapters : []
  adventure.chapters = editorChapters.value.map(chapter => {
    const original = originalChapters.find((candidate: any) => candidate.id === chapter.id) || {}
    return { ...original, id: chapter.id, step_ids: editorSteps.value.filter(step => step.chapter_id === chapter.id).map(step => step.id) }
  })
  adventure.start_step_id = editorStartStepId.value || editorSteps.value[0]?.id || adventure.start_step_id
  adventure.steps = editorSteps.value.map(step => {
    const original = (Array.isArray(adventure.steps) ? adventure.steps : []).find((candidate: any) => candidate.id === step.id) || {}
    return { ...original, id: step.id, chapter_id: step.chapter_id, scene_ref: step.scene_ref, requires: step.requires, encounter_preset_id: step.encounter_preset_id || undefined, choice_ids: editorChoices.value.filter(choice => choice.step_id === step.id).map(choice => choice.id) }
  })
  adventure.choices = editorChoices.value.map(choice => {
    const original = (Array.isArray(adventure.choices) ? adventure.choices : []).find((candidate: any) => candidate.id === choice.id) || {}
    return { ...original, id: choice.id, step_id: choice.step_id, next_step_id: choice.next_step_id }
  })
  const encountersByCatalog = new Map<string, EditorEncounter[]>()
  editorEncounters.value.forEach(encounter => {
    const entries = encountersByCatalog.get(encounter.catalog_path) || []
    entries.push(encounter)
    encountersByCatalog.set(encounter.catalog_path, entries)
  })
  for (const [catalogPath, encounters] of encountersByCatalog) {
    const catalog = (files[catalogPath] ||= {
      schema_version: 1,
      kind: 'encounter_catalog',
      id: catalogPath.split('/').pop()?.replace(/\.json$/, '') || 'adventure_encounters',
      source_ref: `user:${editing.value?.adventure_id || 'adventure'}`,
      automation_level: 'deterministic',
      presets: [],
    }) as Record<string, any>
    const originalPresets = Array.isArray(catalog.presets) ? catalog.presets : []
    catalog.presets = encounters.map(encounter => {
      const original = originalPresets.find((preset: any) => String(preset.id || '') === encounter.id) || {}
      return {
        ...original,
        id: encounter.id,
        difficulty: encounter.difficulty || 'standard',
        enemies: encounter.enemies.map(enemy => {
          const originalEnemy = (Array.isArray(original.enemies) ? original.enemies : []).find((item: any) => String(item.id || '') === enemy.id) || {}
          return {
            ...originalEnemy,
            id: enemy.id,
            profile_id: enemy.profile_id || originalEnemy.profile_id || enemy.id,
            hp: Math.max(1, Number(enemy.hp || 1)),
            armor_class: Math.max(1, Number(enemy.armor_class || 10)),
            attacks: enemy.attacks.map(attack => {
              const originalAttack = (Array.isArray(originalEnemy.attacks) ? originalEnemy.attacks : []).find((item: any) => String(item.id || '') === attack.id) || {}
              return { ...originalAttack, id: attack.id, damage: attack.damage || '1d4', attack_bonus: Number(attack.attack_bonus || 0) }
            }),
          }
        }),
      }
    })
    const catalogId = String(catalog.id || catalogPath.split('/').pop()?.replace(/\.json$/, '') || 'adventure_encounters')
    const encounterLocalePath = `locales/${locale.value}/encounters/${catalogId}.json`
    const encounterLocale = (files[encounterLocalePath] ||= {
      locale_schema_version: 1,
      locale: locale.value,
      target: { kind: 'encounter_catalog', id: catalogId },
      fields: { name: catalogId, labels: { presets: {} } },
    }) as Record<string, any>
    const fields = (encounterLocale.fields ||= {}) as Record<string, any>
    const labels = (fields.labels ||= {}) as Record<string, any>
    const presetLabels = (labels.presets ||= {}) as Record<string, any>
    encounters.forEach(encounter => {
      presetLabels[encounter.id] = { ...(presetLabels[encounter.id] || {}), name: encounter.name, description: encounter.description }
    })
  }
  tutorial.name = editorForm.value.name.trim()
  tutorial.summary = editorForm.value.summary.trim()
  tutorial.chapters ||= {}
  for (const chapter of editorChapters.value) tutorial.chapters[chapter.id] = { ...(tutorial.chapters[chapter.id] || {}), name: chapter.name }
  const oldSteps = tutorial.steps || {}
  tutorial.steps = Object.fromEntries(editorSteps.value.map(step => [step.id, { ...(oldSteps[step.id] || {}), title: step.title, narration: step.narration, objective: step.objective, hint: step.hint }]))
  const oldChoices = tutorial.choices || {}
  tutorial.choices = Object.fromEntries(editorChoices.value.map(choice => [choice.id, { ...(oldChoices[choice.id] || {}), label: choice.label, description: choice.description }]))
  editingFiles.value = files
  filesJson.value = JSON.stringify(files, null, 2)
}

function addStep() {
  const id = `step_${Date.now().toString(36)}`
  const chapterId = editorChapters.value[0]?.id || 'chapter_1'
  if (!editorChapters.value.length) editorChapters.value.push({ id: chapterId, name: '第一章' })
  const previous = [...editorSteps.value].reverse().find(step => step.chapter_id === chapterId)
  editorSteps.value.push({ id, chapter_id: chapterId, scene_ref: '', requires: 'none', encounter_preset_id: '', title: '新步骤', narration: '', objective: '', hint: '' })
  if (previous) connectStepAfter(previous.id, id)
}

function newStep(chapterId: string): EditorStep {
  return { id: `step_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`, chapter_id: chapterId, scene_ref: '', requires: 'none', encounter_preset_id: '', title: '新步骤', narration: '', objective: '', hint: '' }
}

function insertStep(stepId: string, offset: -1 | 1) {
  const index = editorSteps.value.findIndex(step => step.id === stepId)
  if (index < 0) return
  const source = editorSteps.value[index]
  const step = newStep(source.chapter_id)
  editorSteps.value.splice(index + (offset > 0 ? 1 : 0), 0, step)
  if (offset < 0) connectStepBefore(source.id, step.id)
  else connectStepAfter(source.id, step.id)
}

function makeChoice(stepId: string, nextStepId: string, label = '继续'): EditorChoice {
  return { id: `choice_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 5)}`, step_id: stepId, next_step_id: nextStepId, label, description: '' }
}

/** Keep the graph connected when a user inserts a step in the visual order. */
function connectStepBefore(sourceId: string, insertedId: string) {
  const incoming = editorChoices.value.filter(choice => choice.next_step_id === sourceId)
  if (incoming.length) {
    incoming.forEach(choice => { choice.next_step_id = insertedId })
  } else if (editorStartStepId.value === sourceId) {
    editorStartStepId.value = insertedId
  }
  editorChoices.value.push(makeChoice(insertedId, sourceId))
}

function connectStepAfter(sourceId: string, insertedId: string) {
  const outgoing = editorChoices.value.filter(choice => choice.step_id === sourceId)
  if (!outgoing.length) {
    editorChoices.value.push(makeChoice(sourceId, insertedId))
    return
  }
  const continuations = outgoing.map(choice => ({
    ...makeChoice(insertedId, choice.next_step_id, choice.label || '继续'),
    description: choice.description,
  }))
  outgoing.forEach(choice => { choice.next_step_id = insertedId })
  editorChoices.value.push(...continuations)
}

function moveStep(stepId: string, direction: -1 | 1) {
  const index = editorSteps.value.findIndex(step => step.id === stepId)
  if (index < 0) return
  const chapterId = editorSteps.value[index].chapter_id
  const siblings = editorSteps.value
    .map((step, itemIndex) => ({ step, itemIndex }))
    .filter(item => item.step.chapter_id === chapterId)
  const siblingIndex = siblings.findIndex(item => item.step.id === stepId)
  const target = siblings[siblingIndex + direction]
  if (!target) return
  const [moved] = editorSteps.value.splice(index, 1)
  editorSteps.value.splice(target.itemIndex + (direction > 0 ? 0 : 0), 0, moved)
}

function addChoice(stepId: string) {
  const id = `choice_${Date.now().toString(36)}`
  editorChoices.value.push({ id, step_id: stepId, next_step_id: '', label: '新选项', description: '' })
}

function addChapter() {
  const id = `chapter_${editorChapters.value.length + 1}`
  editorChapters.value.push({ id, name: `第 ${editorChapters.value.length + 1} 章` })
}

function removeChapter(chapterId: string) {
  if (editorChapters.value.length <= 1) return
  const fallback = editorChapters.value.find(chapter => chapter.id !== chapterId)?.id || ''
  editorSteps.value.forEach(step => { if (step.chapter_id === chapterId) step.chapter_id = fallback })
  editorChapters.value = editorChapters.value.filter(chapter => chapter.id !== chapterId)
}

function removeStep(stepId: string) {
  if (editorSteps.value.length <= 1) return
  editorSteps.value = editorSteps.value.filter(step => step.id !== stepId)
  editorChoices.value = editorChoices.value.filter(choice => choice.step_id !== stepId && choice.next_step_id !== stepId)
  if (editorStartStepId.value === stepId) editorStartStepId.value = editorSteps.value[0]?.id || ''
}

function removeChoice(choiceId: string) {
  editorChoices.value = editorChoices.value.filter(choice => choice.id !== choiceId)
}

function addEncounter() {
  const catalogPath = editorEncounters.value[0]?.catalog_path || 'content/encounters/adventure_encounters.json'
  editorEncounters.value.push({
    id: `encounter_${Date.now().toString(36)}`,
    name: '新遭遇', difficulty: 'standard', description: '', catalog_path: catalogPath,
    enemies: [],
  })
}

function removeEncounter(encounterId: string) {
  editorEncounters.value = editorEncounters.value.filter(encounter => encounter.id !== encounterId)
  editorSteps.value.forEach(step => { if (step.encounter_preset_id === encounterId) step.encounter_preset_id = '' })
}

function addEnemy(encounter: EditorEncounter) {
  encounter.enemies.push({
    id: `enemy_${Date.now().toString(36)}`,
    profile_id: 'custom_enemy', hp: 10, armor_class: 12,
    attacks: [{ id: 'attack', damage: '1d6+2', attack_bonus: 4 }],
  })
}

function removeEnemy(encounter: EditorEncounter, enemyId: string) {
  encounter.enemies = encounter.enemies.filter(enemy => enemy.id !== enemyId)
}

function addAttack(enemy: EditorEnemy) {
  enemy.attacks.push({ id: `attack_${enemy.attacks.length + 1}`, damage: '1d6+2', attack_bonus: 4 })
}

function removeAttack(enemy: EditorEnemy, attackId: string) {
  if (enemy.attacks.length <= 1) return
  enemy.attacks = enemy.attacks.filter(attack => attack.id !== attackId)
}

async function savePackage() {
  if (!editing.value) return
  busy.value = true
  error.value = ''
  try {
    if (!advancedOpen.value) syncStructuredEditor()
    const files = JSON.parse(filesJson.value || '{}') as Record<string, unknown>
    await api(`/adventures/${encodeURIComponent(editing.value.adventure_id)}`, {
      method: 'PUT',
      body: JSON.stringify({ files, language: locale.value }),
    })
    toast.success(t('adventureUpdated'))
    closeEditor()
    await load()
  } catch (cause: unknown) {
    error.value = cause instanceof SyntaxError ? t('adventureJsonInvalid') : errorMessage(cause)
  } finally {
    busy.value = false
  }
}

async function removePackage(item: AdventureSummary) {
  const accepted = await confirm({
    title: t('deleteAdventurePackage'),
    content: t('deleteAdventurePackageConfirm', { name: item.name || item.adventure_id }),
    positiveText: t('delete'),
    type: 'error',
  })
  if (!accepted) return
  try {
    await api(`/adventures/${encodeURIComponent(item.adventure_id)}`, { method: 'DELETE' })
    toast.success(t('deleted'))
    await load()
  } catch (cause: unknown) {
    error.value = errorMessage(cause)
  }
}

async function exportPackage(item: AdventureSummary) {
  try {
    const response = await apiBlob(`/adventures/${encodeURIComponent(item.adventure_id)}/export`)
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${item.directory_id || 'adventure'}.dfadventure.zip`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (cause: unknown) {
    error.value = errorMessage(cause)
  }
}

async function importPackage(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const body = new FormData()
  body.append('file', file)
  busy.value = true
  try {
    await api('/adventures/import', { method: 'POST', body })
    toast.success(t('adventureImported'))
    await load()
  } catch (cause: unknown) {
    error.value = errorMessage(cause)
  } finally {
    busy.value = false
  }
}

function policyLabel(policy: string) {
  if (policy === 'fixed') return t('adventurePolicyFixed')
  if (policy === 'agnostic') return t('adventurePolicyAgnostic')
  return t('adventurePolicyPortable')
}
</script>

<template>
  <section class="view archive-page rules-page adventures-page">
    <header class="view-title archive-hero">
      <div>
        <span class="section-kicker">{{ t('adventurePackagesKicker') }}</span>
        <h1>{{ t('adventurePackageManagement') }}</h1>
        <p class="muted">{{ t('adventurePackageManagementHint') }}</p>
      </div>
      <div class="actions adventure-header-actions">
        <input ref="importInput" hidden type="file" accept=".zip,.dfadventure" @change="importPackage">
        <button class="primary" @click="openCreate()">{{ t('newAdventurePackage') }}</button>
        <button @click="openAiDraft">{{ t('aiGenerateAdventure') }}</button>
        <button :disabled="busy" @click="importInput?.click()">{{ t('importAdventurePackage') }}</button>
        <button @click="load">{{ t('refresh') }}</button>
      </div>
    </header>

    <p v-if="error" class="error-banner">{{ error }}</p>

    <div class="archive-stats">
      <article><strong>{{ builtinCount }}</strong><span>{{ t('builtinAdventurePackages') }}</span></article>
      <article><strong>{{ customCount }}</strong><span>{{ t('customAdventurePackages') }}</span></article>
      <article><strong>{{ boundCount }}</strong><span>{{ t('boundAdventurePackages') }}</span></article>
    </div>

    <Modal v-if="createOpen" :title="createSource === 'ai' ? t('aiGenerateAdventure') : t('newAdventurePackage')" @close="createOpen = false">
      <div v-if="createSource === 'ai'" class="adventure-create-progress" aria-label="AI adventure creation progress">
        <span :class="{ active: createStep === 1 }">1 · {{ String(locale).startsWith('zh') ? '描述构想' : 'Describe' }}</span>
        <span :class="{ active: createStep === 2 }">2 · {{ String(locale).startsWith('zh') ? '确认摘要' : 'Review' }}</span>
        <span>3 · {{ String(locale).startsWith('zh') ? '结构化编辑' : 'Edit' }}</span>
      </div>
      <template v-if="createSource === 'ai' && createStep === 1">
        <p class="muted">{{ t('aiGenerateAdventureHint') }}</p>
        <label>{{ t('aiAdventurePrompt') }}<textarea v-model="aiPrompt" rows="7" :placeholder="t('aiAdventurePromptPlaceholder')"></textarea></label>
      </template>
      <template v-else>
        <p class="muted">{{ createSource === 'ai' ? (String(locale).startsWith('zh') ? '草稿只会先进入结构化编辑器；确认保存前不会成为最终内容。' : 'The draft enters the structured editor before final validation and save.') : t('newAdventurePackageHint') }}</p>
        <div v-if="createSource === 'ai'" class="adventure-ai-summary">
          <strong>{{ createForm.name || t('newAdventureNamePlaceholder') }}</strong>
          <span>{{ createForm.summary || t('noDescription') }}</span>
          <small>{{ aiDraftCounts.chapters }} {{ String(locale).startsWith('zh') ? '章' : 'chapters' }} · {{ aiDraftCounts.steps }} {{ String(locale).startsWith('zh') ? '个步骤' : 'steps' }} · {{ aiDraftCounts.encounters }} {{ String(locale).startsWith('zh') ? '个遭遇' : 'encounters' }}</small>
        </div>
        <div class="grid-2">
          <label v-if="createSource === 'manual'">{{ t('directoryId') }}<input v-model="createForm.directory_id" placeholder="my_adventure"></label>
          <label v-if="createSource === 'manual'">{{ t('canonicalAdventureId') }}<input v-model="createForm.adventure_id" :placeholder="createForm.directory_id ? `user:${createForm.directory_id}` : 'user:my_adventure'"></label>
          <label>{{ t('adventurePackageName') }}<input v-model="createForm.name" :placeholder="t('newAdventureNamePlaceholder')"></label>
          <label>{{ t('version') }}<input v-model="createForm.version"></label>
          <label>{{ t('adventureWorldPolicy') }}<select v-model="createForm.world_policy"><option value="portable">{{ t('adventurePolicyPortable') }}</option><option value="agnostic">{{ t('adventurePolicyAgnostic') }}</option><option value="fixed">{{ t('adventurePolicyFixed') }}</option></select></label>
          <label>{{ t('estimatedMinutes') }}<input v-model.number="createForm.estimated_minutes" type="number" min="1" max="999"></label>
          <label v-if="createForm.world_policy === 'fixed'">{{ t('recommendedWorldBook') }}<select v-model="createForm.recommended_world_id"><option value="">{{ t('selectWorld') }}</option><option v-for="world in worlds" :key="worldId(world)" :value="worldId(world)">{{ worldLabel(world) }}</option></select></label>
        </div>
        <label>{{ t('summary') }}<textarea v-model="createForm.summary" rows="4"></textarea></label>
      </template>
      <template #actions>
        <button @click="createOpen = false">{{ t('cancel') }}</button>
        <button v-if="createSource === 'ai' && createStep === 2" @click="createStep = 1">{{ String(locale).startsWith('zh') ? '上一步' : 'Back' }}</button>
        <button v-if="createSource === 'ai' && createStep === 1" class="primary" :disabled="aiBusy || !aiPrompt.trim()" @click="generateDraft">{{ aiBusy ? t('generating') : t('generateDraft') }}</button>
        <button v-else class="primary" :disabled="busy || !createForm.name || (createSource === 'manual' && !createForm.directory_id)" @click="createPackage">{{ createSource === 'ai' ? (String(locale).startsWith('zh') ? '进入结构化编辑' : 'Open structured editor') : t('createAdventurePackage') }}</button>
      </template>
    </Modal>

    <div class="adventure-boundary-note">
      <strong>{{ t('worldbookAdventureBoundary') }}</strong>
      <span>{{ t('worldbookAdventureBoundaryHint') }}</span>
      <small>{{ t('adventurePackagesDndOnly') }}</small>
    </div>

    <div class="card-grid">
      <article v-for="item in items" :key="item.adventure_id" class="rule-card adventure-package-card">
        <div>
          <header class="adventure-package-heading">
            <div class="adventure-package-title-row">
              <h2 :title="item.name || item.adventure_id">{{ item.name || item.adventure_id }}</h2>
              <small :class="['badge', item.custom ? 'badge-active' : '']">{{ item.custom ? t('custom') : t('builtin') }}</small>
            </div>
            <div class="adventure-package-badges">
              <small v-if="item.required_runtime?.id === 'core:dnd2024'" class="badge badge-beta">{{ t('advancedRulesBeta') }}</small>
            </div>
          </header>
          <div class="rule-meta-row">
            <span><strong>{{ t('version') }}</strong>{{ item.version }}</span>
            <span><strong>{{ t('adventureWorldPolicy') }}</strong>{{ policyLabel(item.world_policy) }}</span>
            <span><strong>{{ t('saveBindingCount') }}</strong>{{ item.in_use || 0 }}</span>
            <span><strong>ID</strong>{{ item.adventure_id }}</span>
          </div>
          <p>{{ item.summary || t('noDescription') }}</p>
          <small v-if="item.recommended_world_id" class="muted">{{ t('recommendedWorldBook') }}：{{ item.recommended_world_id }}</small>
          <small v-if="item.in_use" class="adventure-lock-note">{{ t('adventureBoundReadOnly') }}</small>
        </div>
        <div class="actions adventure-package-actions">
          <button @click="openCopy(item)">{{ t('copyAndEdit') }}</button>
          <button @click="exportPackage(item)">{{ t('export') }}</button>
          <button v-if="item.custom" :disabled="!item.editable" @click="openEditor(item)">{{ t('edit') }}</button>
          <button v-if="item.custom" class="danger" :disabled="!item.editable" @click="removePackage(item)">{{ t('delete') }}</button>
        </div>
      </article>
      <p v-if="!items.length" class="muted">{{ t('noAdventurePackages') }}</p>
    </div>

    <Modal v-if="copySource" :title="t('copyAdventurePackage')" @close="copySource = null">
      <p class="muted">{{ t('copyAdventurePackageHint') }}</p>
      <div class="grid-2">
        <label>{{ t('directoryId') }}<input v-model="copyForm.directory_id"></label>
        <label>{{ t('canonicalAdventureId') }}<input v-model="copyForm.adventure_id"></label>
        <label>{{ t('adventurePackageName') }}<input v-model="copyForm.name"></label>
        <label>{{ t('version') }}<input v-model="copyForm.version"></label>
      </div>
      <label>{{ t('summary') }}<textarea v-model="copyForm.summary" rows="4" /></label>
      <template #actions>
        <button @click="copySource = null">{{ t('cancel') }}</button>
        <button class="primary" :disabled="busy" @click="copyPackage">{{ t('copyAdventurePackage') }}</button>
      </template>
    </Modal>

    <Modal v-if="editing" :title="editingCreation ? `${t('editAdventurePackage')} · 3/3` : t('editAdventurePackage')" dialog-class="adventure-editor-dialog" @close="cancelEditor">
      <p class="muted">{{ t('adventureStructuredEditorHint') }}</p>
      <section class="adventure-editor-form">
        <nav class="adventure-editor-nav" aria-label="Adventure editor sections">
          <button type="button" :class="{ active: editorPanel === 'overview' }" @click="editorPanel = 'overview'">{{ String(locale).startsWith('zh') ? '概览' : 'Overview' }}</button>
          <button type="button" :class="{ active: editorPanel === 'flow' }" @click="editorPanel = 'flow'">{{ String(locale).startsWith('zh') ? '流程' : 'Flow' }} <span>{{ editorSteps.length }}</span><em v-if="editorGraphIssues.length">!</em></button>
          <button type="button" :class="{ active: editorPanel === 'encounters' }" @click="editorPanel = 'encounters'">{{ String(locale).startsWith('zh') ? '遭遇' : 'Encounters' }} <span>{{ editorEncounters.length }}</span></button>
          <button type="button" :class="{ active: editorPanel === 'preview' }" @click="editorPanel = 'preview'">{{ String(locale).startsWith('zh') ? '预览' : 'Preview' }}</button>
          <button type="button" :class="{ active: editorPanel === 'advanced' }" @click="editorPanel = 'advanced'">JSON</button>
        </nav>
        <section v-if="['overview', 'flow', 'encounters'].includes(editorPanel)" class="adventure-editor-ai-bar">
          <div class="adventure-editor-ai-copy">
            <strong>{{ editorAiPanelTitle() }}</strong>
            <small>{{ String(locale).startsWith('zh') ? '用自然语言描述即可。AI 只会修改当前分区，结果先填入草稿，检查无误后再保存。' : 'Describe what you want in plain language. Only this section is changed; review the draft before saving.' }}</small>
          </div>
          <div class="adventure-editor-ai-controls">
            <textarea v-model="editorAiPrompt" rows="2" :placeholder="editorAiPlaceholder()" :disabled="editorAiBusy"></textarea>
            <button type="button" class="secondary" :disabled="editorAiBusy || !editorAiPrompt.trim()" @click="generateEditorPanelDraft">{{ editorAiBusy ? (String(locale).startsWith('zh') ? '生成中…' : 'Generating…') : (String(locale).startsWith('zh') ? 'AI 生成并填入' : 'Generate with AI') }}</button>
          </div>
        </section>
        <div v-if="editorGraphIssues.length" class="adventure-editor-issue-strip">
          <strong>{{ String(locale).startsWith('zh') ? `${editorGraphIssues.length} 个流程问题` : `${editorGraphIssues.length} flow issues` }}</strong>
          <button type="button" @click="editorPanel = 'flow'">{{ String(locale).startsWith('zh') ? '去流程区处理' : 'Review flow' }}</button>
        </div>
        <div v-if="editorPanel === 'overview'" class="adventure-editor-panel-content">
        <div class="grid-2">
          <label>{{ t('adventurePackageName') }}<input v-model="editorForm.name"></label>
          <label>{{ t('version') }}<input v-model="editorForm.version"></label>
          <label>{{ t('adventureWorldPolicy') }}<select v-model="editorForm.world_policy"><option value="portable">{{ t('adventurePolicyPortable') }}</option><option value="agnostic">{{ t('adventurePolicyAgnostic') }}</option><option value="fixed">{{ t('adventurePolicyFixed') }}</option></select></label>
          <label>{{ t('estimatedMinutes') }}<input v-model.number="editorForm.estimated_minutes" type="number" min="1" max="999"></label>
          <label v-if="editorForm.world_policy === 'fixed'">{{ t('recommendedWorldBook') }}<select v-model="editorForm.recommended_world_id"><option value="">{{ t('selectWorld') }}</option><option v-for="world in worlds" :key="worldId(world)" :value="worldId(world)">{{ worldLabel(world) }}</option></select></label>
        </div>
        <label>{{ t('summary') }}<textarea v-model="editorForm.summary" rows="3"></textarea></label>
        <label class="adventure-start-step">
          <span>{{ String(locale).startsWith('zh') ? '冒险起点' : 'Adventure start' }}</span>
          <select v-model="editorStartStepId">
            <option v-for="step in editorSteps" :key="step.id" :value="step.id">{{ step.title || t('unnamedStep') }}</option>
          </select>
          <small>{{ String(locale).startsWith('zh') ? '新增或移动步骤不会自动改变入口；请在这里明确选择第一步。' : 'Adding or moving steps will not silently change the entry point.' }}</small>
        </label>
        <section v-if="editorGraphIssues.length" class="adventure-editor-diagnostics" role="status">
          <strong>{{ String(locale).startsWith('zh') ? '流程检查' : 'Flow checks' }}</strong>
          <ul><li v-for="issue in editorGraphIssues" :key="issue">{{ issue }}</li></ul>
          <small>{{ String(locale).startsWith('zh') ? '保存时服务端还会执行完整校验。' : 'The server performs a final validation when you save.' }}</small>
        </section>
        </div>
        <section v-if="editorPanel === 'encounters'" class="adventure-encounter-editor adventure-editor-panel-content">
          <header class="adventure-editor-section-head">
            <div>
              <strong>{{ String(locale).startsWith('zh') ? '战斗遭遇与怪物' : 'Combat encounters and monsters' }}</strong>
              <small>{{ String(locale).startsWith('zh') ? '遭遇是冒险中的可复用战斗配置；规则结算仍由 D&D 运行时负责。' : 'Encounters are reusable combat configurations; the D&D runtime owns resolution.' }}</small>
            </div>
            <button type="button" class="secondary" @click="addEncounter">{{ String(locale).startsWith('zh') ? '新增遭遇' : 'Add encounter' }}</button>
          </header>
          <p v-if="!editorEncounters.length" class="muted">{{ String(locale).startsWith('zh') ? '还没有遭遇。新增后可在步骤中绑定它。' : 'No encounters yet. Add one, then bind it to a step.' }}</p>
          <article v-for="encounter in editorEncounters" :key="encounter.id" class="adventure-encounter-card">
            <header class="adventure-encounter-head">
              <div class="adventure-encounter-title-fields">
                <label>{{ String(locale).startsWith('zh') ? '遭遇名称' : 'Encounter name' }}<input v-model="encounter.name" :placeholder="String(locale).startsWith('zh') ? '例如：荆棘林伏击' : 'e.g. Thorn glade ambush'"></label>
                <label>{{ String(locale).startsWith('zh') ? '难度' : 'Difficulty' }}<select v-model="encounter.difficulty">
                <option value="story">{{ String(locale).startsWith('zh') ? '剧情' : 'Story' }}</option>
                <option value="standard">{{ String(locale).startsWith('zh') ? '标准' : 'Standard' }}</option>
                <option value="challenging">{{ String(locale).startsWith('zh') ? '挑战' : 'Challenging' }}</option>
                <option value="lethal">{{ String(locale).startsWith('zh') ? '致命' : 'Lethal' }}</option>
                </select></label>
              </div>
              <button type="button" class="link-button danger-text" @click="removeEncounter(encounter.id)">{{ String(locale).startsWith('zh') ? '删除遭遇' : 'Delete encounter' }}</button>
            </header>
            <textarea v-model="encounter.description" rows="2" :placeholder="String(locale).startsWith('zh') ? '遭遇说明（不会替代世界书）' : 'Encounter description (does not replace the worldbook)'"></textarea>
            <div class="adventure-enemy-list">
            <article v-for="(enemy, enemyIndex) in encounter.enemies" :key="enemy.id" class="adventure-enemy-card">
              <header class="adventure-enemy-head"><strong>{{ String(locale).startsWith('zh') ? `怪物 ${enemyIndex + 1}` : `Monster ${enemyIndex + 1}` }}</strong><button type="button" class="link-button danger-text" @click="removeEnemy(encounter, enemy.id)">{{ String(locale).startsWith('zh') ? '删除怪物' : 'Delete monster' }}</button></header>
              <div class="adventure-enemy-stats">
                <label>{{ String(locale).startsWith('zh') ? '怪物 ID' : 'Monster ID' }}<input v-model="enemy.profile_id" :placeholder="String(locale).startsWith('zh') ? '例如：goblin' : 'e.g. goblin'"></label>
                <label>HP<input v-model.number="enemy.hp" type="number" min="1"></label>
                <label>AC<input v-model.number="enemy.armor_class" type="number" min="1"></label>
              </div>
              <section class="adventure-attack-editor"><header><strong>{{ String(locale).startsWith('zh') ? '攻击动作' : 'Attacks' }}</strong><button type="button" class="link-button" @click="addAttack(enemy)">{{ String(locale).startsWith('zh') ? '新增攻击' : 'Add attack' }}</button></header>
                <div v-for="attack in enemy.attacks" :key="attack.id" class="adventure-attack-row">
                  <label>{{ String(locale).startsWith('zh') ? '攻击 ID' : 'Attack ID' }}<input v-model="attack.id" placeholder="claw"></label>
                  <label>{{ String(locale).startsWith('zh') ? '伤害骰' : 'Damage' }}<input v-model="attack.damage" placeholder="1d6+2"></label>
                  <label>{{ String(locale).startsWith('zh') ? '命中加值' : 'Bonus' }}<input v-model.number="attack.attack_bonus" type="number"></label>
                  <button type="button" class="link-button danger-text" @click="removeAttack(enemy, attack.id)">{{ String(locale).startsWith('zh') ? '删除' : 'Remove' }}</button>
                </div>
              </section>
            </article>
            </div>
            <button type="button" class="link-button" @click="addEnemy(encounter)">{{ String(locale).startsWith('zh') ? '新增怪物' : 'Add monster' }}</button>
          </article>
        </section>
        <div v-if="editorPanel === 'flow'" class="adventure-editor-panel-content adventure-flow-panel">
        <section class="adventure-flow-map" aria-label="Adventure flow overview">
          <header><strong>{{ String(locale).startsWith('zh') ? '流程概览' : 'Flow overview' }}</strong><small>{{ String(locale).startsWith('zh') ? '先看结构，再编辑下面的节点。' : 'Understand the structure before editing node details.' }}</small></header>
          <div class="adventure-flow-track">
            <template v-for="item in editorFlowPreview" :key="item.step.id">
              <article :class="['adventure-flow-node', { start: item.step.id === editorStartStepId }]">
                <small>{{ item.index + 1 }} · {{ item.step.chapter_id }}</small>
                <strong>{{ item.step.title || t('unnamedStep') }}</strong>
                <span v-if="item.step.id === editorStartStepId">{{ String(locale).startsWith('zh') ? '起点' : 'Start' }}</span>
                <div v-if="item.outgoing.length" class="adventure-flow-edges">
                  <i v-for="edge in item.outgoing" :key="`${item.step.id}-${edge.label}-${edge.target}`">{{ edge.label }} → {{ edge.target }}</i>
                </div>
                <em v-else>{{ String(locale).startsWith('zh') ? '结局' : 'End' }}</em>
              </article>
              <b v-if="item.index < editorFlowPreview.length - 1" class="adventure-flow-arrow" aria-hidden="true">→</b>
            </template>
          </div>
        </section>
        <div v-for="chapter in editorChapters" :key="chapter.id" class="adventure-chapter-editor">
          <div class="adventure-editor-section-head"><input v-model="chapter.name" :aria-label="t('adventureChapter')"><button v-if="editorChapters.length > 1" type="button" class="link-button danger-text" @click="removeChapter(chapter.id)">{{ t('deleteChapter') }}</button></div>
          <div class="adventure-step-list">
          <article v-for="step in editorSteps.filter(item => item.chapter_id === chapter.id)" :key="step.id" class="adventure-step-editor">
            <header>
              <strong>{{ step.title || t('unnamedStep') }}</strong>
              <span class="editor-step-index">{{ t('step') }}</span>
              <button type="button" class="link-button" @click="insertStep(step.id, -1)">{{ String(locale).startsWith('zh') ? '前面插入' : 'Insert before' }}</button>
              <button type="button" class="link-button" @click="insertStep(step.id, 1)">{{ String(locale).startsWith('zh') ? '后面插入' : 'Insert after' }}</button>
              <button type="button" class="link-button" @click="moveStep(step.id, -1)">{{ String(locale).startsWith('zh') ? '上移' : 'Move up' }}</button>
              <button type="button" class="link-button" @click="moveStep(step.id, 1)">{{ String(locale).startsWith('zh') ? '下移' : 'Move down' }}</button>
              <button type="button" class="link-button" @click="addChoice(step.id)">{{ t('addChoice') }}</button>
              <button v-if="editorSteps.length > 1" type="button" class="link-button danger-text" @click="removeStep(step.id)">{{ t('deleteStep') }}</button>
            </header>
            <div class="grid-2">
              <label>{{ t('stepTitle') }}<input v-model="step.title"></label>
              <label>{{ t('sceneReference') }}<select v-model="step.scene_ref"><option value="">{{ t('sceneNotLinked') }}</option><option v-for="scene in editorScenes" :key="scene.ref" :value="scene.ref">{{ scene.name }}</option></select></label>
            </div>
            <label v-if="editorEncounters.length" class="adventure-step-encounter">
              <span>{{ String(locale).startsWith('zh') ? '战斗遭遇（可选）' : 'Combat encounter (optional)' }}</span>
              <select v-model="step.encounter_preset_id">
                <option value="">{{ String(locale).startsWith('zh') ? '非战斗步骤' : 'No combat encounter' }}</option>
                <option v-for="encounter in editorEncounters" :key="encounter.id" :value="encounter.id">{{ encounter.name }} · {{ encounter.difficulty }}</option>
              </select>
              <small v-if="step.encounter_preset_id">{{ editorEncounters.find(item => item.id === step.encounter_preset_id)?.description }}</small>
            </label>
            <label>{{ t('narration') }}<textarea v-model="step.narration" rows="2"></textarea></label>
            <div class="grid-2">
              <label>{{ t('objective') }}<input v-model="step.objective"></label>
              <label>{{ t('hint') }}<input v-model="step.hint"></label>
            </div>
            <div v-for="choice in editorChoices.filter(item => item.step_id === step.id)" :key="choice.id" class="adventure-choice-editor">
              <input v-model="choice.label" :placeholder="t('choiceLabel')"><select v-model="choice.next_step_id"><option value="">{{ t('endAdventure') }}</option><option v-for="target in editorSteps" :key="target.id" :value="target.id">{{ target.title || t('unnamedStep') }}</option></select><input v-model="choice.description" :placeholder="t('choiceDescription')"><button type="button" class="link-button danger-text" @click="removeChoice(choice.id)">{{ t('deleteChoice') }}</button>
            </div>
          </article>
          <p v-if="!editorSteps.some(item => item.chapter_id === chapter.id)" class="muted">{{ t('noStepsInChapter') }}</p>
          </div>
        </div>
        <div class="adventure-editor-actions"><button type="button" class="secondary" @click="addChapter">{{ t('addChapter') }}</button><button type="button" class="secondary" @click="addStep">{{ t('addStep') }}</button></div>
        </div>
      </section>
      <section v-if="editorPanel === 'preview'" class="adventure-structure-summary adventure-editor-panel-content">
        <header><strong>冒险包结构</strong><span>{{ Object.keys(editingFiles).length }} 个 JSON 文件</span></header>
        <div v-for="group in editingFileGroups" :key="group.label" class="adventure-file-group">
          <b>{{ group.label }}（{{ group.paths.length }}）</b>
          <span v-for="path in group.paths" :key="path">{{ path }}</span>
        </div>
        <small>冒险包由清单、剧情图、场景/NPC/遭遇等内容和多语言文本组成；规则结算仍由规则系统负责。</small>
      </section>
      <details v-if="editorPanel === 'advanced'" class="adventure-advanced-editor adventure-editor-panel-content" open>
        <summary @click.prevent="advancedOpen = !advancedOpen">{{ t('advancedJsonEditor') }}</summary>
        <p class="muted">{{ t('adventureEditorHint') }}</p>
        <textarea v-model="filesJson" class="adventure-package-json" rows="24" spellcheck="false" />
      </details>
      <template #actions>
        <button @click="cancelEditor">{{ editingCreation && String(locale).startsWith('zh') ? '取消并丢弃草稿' : t('cancel') }}</button>
        <button class="primary" :disabled="busy || editorGraphIssues.length > 0" @click="savePackage">{{ t('validateAndSave') }}</button>
      </template>
    </Modal>
  </section>
</template>
