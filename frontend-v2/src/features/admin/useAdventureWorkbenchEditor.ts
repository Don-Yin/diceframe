import type { Ref } from 'vue'
import type { AdventureSummary } from '@/api/types'
import type { ScriptFiles } from '@/features/adventures/scriptTypes'
import type {
  EditorChapter,
  EditorChoice,
  EditorEncounter,
  EditorEnemy,
  EditorScene,
  EditorStep,
} from './adventureEditorGraph'

export type StructuredEditorForm = {
  name: string
  summary: string
  version: string
  world_policy: string
  recommended_world_id: string
  estimated_minutes: number
}

/**
 * Owns the structured adventure editor's document projection and mutations.
 * The workbench page remains the orchestrator for loading/saving and modal
 * routing; this module owns only the editable graph/document state.
 */
export function useAdventureWorkbenchEditor(options: {
  locale: Ref<string>
  editing: Ref<AdventureSummary | null>
  editingFiles: Ref<Record<string, unknown>>
  filesJson: Ref<string>
  editorForm: Ref<StructuredEditorForm>
  editorSteps: Ref<EditorStep[]>
  editorChoices: Ref<EditorChoice[]>
  editorChapters: Ref<EditorChapter[]>
  editorScenes: Ref<EditorScene[]>
  editorEncounters: Ref<EditorEncounter[]>
  editorStartStepId: Ref<string>
}) {
  const {
    locale, editing, editingFiles, filesJson, editorForm, editorSteps,
    editorChoices, editorChapters, editorScenes, editorEncounters, editorStartStepId,
  } = options

  function hydrateStructuredEditor() {
    const files = editingFiles.value as ScriptFiles
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
        const sceneLocale = (files[`locales/${locale.value}/scenes/${sceneId}.json`] || files['locales/zh-CN/scenes/' + sceneId + '.json'] || {}) as Record<string, any>
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
        const encounterLocale = (files[`locales/${locale.value}/encounters/${catalogId}.json`] || files[`locales/zh-CN/encounters/${catalogId}.json`] || {}) as Record<string, any>
        const labels = (encounterLocale.fields?.labels?.presets || {}) as Record<string, any>
        return (Array.isArray(catalog.presets) ? catalog.presets : []).map((preset: any) => {
          const id = String(preset.id || '')
          const label = labels[id] as Record<string, any> | undefined
          return {
            id, name: String(label?.name || id || '未命名遭遇'), difficulty: String(preset.difficulty || 'standard'),
            description: String(label?.description || ''), catalog_path: path,
            enemies: (Array.isArray(preset.enemies) ? preset.enemies : []).map((enemy: any, enemyIndex: number) => ({
              id: String(enemy.id || `enemy_${enemyIndex + 1}`), profile_id: String(enemy.profile_id || ''),
              hp: Math.max(1, Number(enemy.hp || 1)), armor_class: Math.max(1, Number(enemy.armor_class || 10)),
              attacks: (Array.isArray(enemy.attacks) ? enemy.attacks : []).map((attack: any, attackIndex: number) => ({
                id: String(attack.id || `attack_${attackIndex + 1}`), damage: String(attack.damage || '1d4'), attack_bonus: Number(attack.attack_bonus || 0),
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
      const catalog = (files[catalogPath] ||= { schema_version: 1, kind: 'encounter_catalog', id: catalogPath.split('/').pop()?.replace(/\.json$/, '') || 'adventure_encounters', source_ref: `user:${editing.value?.adventure_id || 'adventure'}`, automation_level: 'deterministic', presets: [] }) as Record<string, any>
      const originalPresets = Array.isArray(catalog.presets) ? catalog.presets : []
      catalog.presets = encounters.map(encounter => {
        const original = originalPresets.find((preset: any) => String(preset.id || '') === encounter.id) || {}
        return { ...original, id: encounter.id, difficulty: encounter.difficulty || 'standard', enemies: encounter.enemies.map(enemy => {
          const originalEnemy = (Array.isArray(original.enemies) ? original.enemies : []).find((item: any) => String(item.id || '') === enemy.id) || {}
          return { ...originalEnemy, id: enemy.id, profile_id: enemy.profile_id || originalEnemy.profile_id || enemy.id, hp: Math.max(1, Number(enemy.hp || 1)), armor_class: Math.max(1, Number(enemy.armor_class || 10)), attacks: enemy.attacks.map(attack => {
            const originalAttack = (Array.isArray(originalEnemy.attacks) ? originalEnemy.attacks : []).find((item: any) => String(item.id || '') === attack.id) || {}
            return { ...originalAttack, id: attack.id, damage: attack.damage || '1d4', attack_bonus: Number(attack.attack_bonus || 0) }
          }) }
        }) }
      })
      const catalogId = String(catalog.id || catalogPath.split('/').pop()?.replace(/\.json$/, '') || 'adventure_encounters')
      const encounterLocalePath = `locales/${locale.value}/encounters/${catalogId}.json`
      const encounterLocale = (files[encounterLocalePath] ||= { locale_schema_version: 1, locale: locale.value, target: { kind: 'encounter_catalog', id: catalogId }, fields: { name: catalogId, labels: { presets: {} } } }) as Record<string, any>
      const fields = (encounterLocale.fields ||= {}) as Record<string, any>
      const labels = (fields.labels ||= {}) as Record<string, any>
      const presetLabels = (labels.presets ||= {}) as Record<string, any>
      encounters.forEach(encounter => { presetLabels[encounter.id] = { ...(presetLabels[encounter.id] || {}), name: encounter.name, description: encounter.description } })
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

  function newStep(chapterId: string): EditorStep {
    return { id: `step_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`, chapter_id: chapterId, scene_ref: '', requires: 'none', encounter_preset_id: '', title: '新步骤', narration: '', objective: '', hint: '' }
  }
  function makeChoice(stepId: string, nextStepId: string, label = '继续'): EditorChoice {
    return { id: `choice_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 5)}`, step_id: stepId, next_step_id: nextStepId, label, description: '' }
  }
  function connectStepBefore(sourceId: string, insertedId: string) {
    const incoming = editorChoices.value.filter(choice => choice.next_step_id === sourceId)
    if (incoming.length) incoming.forEach(choice => { choice.next_step_id = insertedId })
    else if (editorStartStepId.value === sourceId) editorStartStepId.value = insertedId
    editorChoices.value.push(makeChoice(insertedId, sourceId))
  }
  function connectStepAfter(sourceId: string, insertedId: string) {
    const outgoing = editorChoices.value.filter(choice => choice.step_id === sourceId)
    if (!outgoing.length) { editorChoices.value.push(makeChoice(sourceId, insertedId)); return }
    const continuations = outgoing.map(choice => ({ ...makeChoice(insertedId, choice.next_step_id, choice.label || '继续'), description: choice.description }))
    outgoing.forEach(choice => { choice.next_step_id = insertedId })
    editorChoices.value.push(...continuations)
  }
  function addStep() {
    const id = `step_${Date.now().toString(36)}`
    const chapterId = editorChapters.value[0]?.id || 'chapter_1'
    if (!editorChapters.value.length) editorChapters.value.push({ id: chapterId, name: '第一章' })
    const previous = [...editorSteps.value].reverse().find(step => step.chapter_id === chapterId)
    editorSteps.value.push({ id, chapter_id: chapterId, scene_ref: '', requires: 'none', encounter_preset_id: '', title: '新步骤', narration: '', objective: '', hint: '' })
    if (previous) connectStepAfter(previous.id, id)
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
  function moveStep(stepId: string, direction: -1 | 1) {
    const index = editorSteps.value.findIndex(step => step.id === stepId)
    if (index < 0) return
    const chapterId = editorSteps.value[index].chapter_id
    const siblings = editorSteps.value.map((step, itemIndex) => ({ step, itemIndex })).filter(item => item.step.chapter_id === chapterId)
    const siblingIndex = siblings.findIndex(item => item.step.id === stepId)
    const target = siblings[siblingIndex + direction]
    if (!target) return
    const [moved] = editorSteps.value.splice(index, 1)
    editorSteps.value.splice(target.itemIndex, 0, moved)
  }
  function addChoice(stepId: string) { editorChoices.value.push({ id: `choice_${Date.now().toString(36)}`, step_id: stepId, next_step_id: '', label: '新选项', description: '' }) }
  function addChapter() { const id = `chapter_${editorChapters.value.length + 1}`; editorChapters.value.push({ id, name: `第 ${editorChapters.value.length + 1} 章` }) }
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
  function removeChoice(choiceId: string) { editorChoices.value = editorChoices.value.filter(choice => choice.id !== choiceId) }
  function addEncounter() {
    const catalogPath = editorEncounters.value[0]?.catalog_path || 'content/encounters/adventure_encounters.json'
    editorEncounters.value.push({ id: `encounter_${Date.now().toString(36)}`, name: '新遭遇', difficulty: 'standard', description: '', catalog_path: catalogPath, enemies: [] })
  }
  function removeEncounter(encounterId: string) {
    editorEncounters.value = editorEncounters.value.filter(encounter => encounter.id !== encounterId)
    editorSteps.value.forEach(step => { if (step.encounter_preset_id === encounterId) step.encounter_preset_id = '' })
  }
  function addEnemy(encounter: EditorEncounter) { encounter.enemies.push({ id: `enemy_${Date.now().toString(36)}`, profile_id: 'custom_enemy', hp: 10, armor_class: 12, attacks: [{ id: 'attack', damage: '1d6+2', attack_bonus: 4 }] }) }
  function removeEnemy(encounter: EditorEncounter, enemyId: string) { encounter.enemies = encounter.enemies.filter(enemy => enemy.id !== enemyId) }
  function addAttack(enemy: EditorEnemy) { enemy.attacks.push({ id: `attack_${enemy.attacks.length + 1}`, damage: '1d6+2', attack_bonus: 4 }) }
  function removeAttack(enemy: EditorEnemy, attackId: string) { if (enemy.attacks.length > 1) enemy.attacks = enemy.attacks.filter(attack => attack.id !== attackId) }

  return {
    hydrateStructuredEditor, syncStructuredEditor, makeChoice, addStep, insertStep, moveStep, addChoice,
    addChapter, removeChapter, removeStep, removeChoice, addEncounter, removeEncounter,
    addEnemy, removeEnemy, addAttack, removeAttack,
  }
}
