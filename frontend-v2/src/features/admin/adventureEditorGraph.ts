import { computed, type Ref } from 'vue'

export type EditorStep = { id: string; chapter_id: string; scene_ref: string; requires: string; encounter_preset_id: string; title: string; narration: string; objective: string; hint: string }
export type EditorChoice = { id: string; step_id: string; next_step_id: string; label: string; description: string }
export type EditorChapter = { id: string; name: string }
export type EditorScene = { ref: string; name: string }
export type EditorAttack = { id: string; damage: string; attack_bonus: number }
export type EditorEnemy = { id: string; profile_id: string; hp: number; armor_class: number; attacks: EditorAttack[] }
export type EditorEncounter = { id: string; name: string; difficulty: string; description: string; catalog_path: string; enemies: EditorEnemy[] }

/** Owns graph-only validation/projection for the adventure workbench. */
export function useAdventureEditorGraph(
  steps: Ref<EditorStep[]>, choices: Ref<EditorChoice[]>, chapters: Ref<EditorChapter[]>,
  encounters: Ref<EditorEncounter[]>, startStepId: Ref<string>, locale: Ref<string>,
) {
  const graphIssues = computed(() => {
    const stepIds = new Set(steps.value.map(step => step.id))
    const chapterIds = new Set(chapters.value.map(chapter => chapter.id))
    const encounterIds = new Set(encounters.value.map(encounter => encounter.id))
    const issues: string[] = []
    if (!startStepId.value || !stepIds.has(startStepId.value)) issues.push(String(locale.value).startsWith('zh') ? '未选择有效的冒险起点。' : 'Choose a valid adventure start step.')
    steps.value.forEach(step => {
      if (!chapterIds.has(step.chapter_id)) issues.push(`步骤「${step.title || step.id}」没有有效章节。`)
      if (step.encounter_preset_id && !encounterIds.has(step.encounter_preset_id)) issues.push(`步骤「${step.title || step.id}」引用了不存在的遭遇。`)
    })
    const incoming = new Set<string>()
    choices.value.forEach(choice => {
      if (!stepIds.has(choice.step_id)) issues.push(`选项「${choice.label || choice.id}」没有有效来源步骤。`)
      if (choice.next_step_id) {
        if (!stepIds.has(choice.next_step_id)) issues.push(`选项「${choice.label || choice.id}」跳转目标不存在。`)
        else incoming.add(choice.next_step_id)
      }
    })
    steps.value.forEach(step => { if (step.id !== startStepId.value && !incoming.has(step.id)) issues.push(`步骤「${step.title || step.id}」从起点不可达。`) })
    return [...new Set(issues)]
  })
  const flowPreview = computed(() => steps.value.map((step, index) => ({
    step, index,
    outgoing: choices.value.filter(choice => choice.step_id === step.id).map(choice => ({
      label: choice.label || '继续', target: steps.value.find(item => item.id === choice.next_step_id)?.title || (choice.next_step_id ? choice.next_step_id : '结局'),
    })),
  })))
  return { graphIssues, flowPreview }
}
