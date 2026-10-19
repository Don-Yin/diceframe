import { computed, ref, watch, type Ref } from 'vue'
import type { Player } from '@/api/types'

const PREFIX = 'diceframe:action-skill:v1:'
const MAX_AGE = 24 * 60 * 60 * 1000

/** Browser-local choice, scoped exactly like the action draft; never a bonus. */
export function useActionSkill(identity: Ref<string>, player: Ref<Player | undefined>) {
  const skills = computed(() => [...new Set((player.value?.character_sheet?.skills || []).map(skill =>
    typeof skill === 'string' ? skill : skill.name,
  ).filter(name => typeof name === 'string' && name.length > 0 && name.length <= 128))])
  const key = () => PREFIX + encodeURIComponent(identity.value)
  function read(): string {
    try {
      const value = JSON.parse(sessionStorage.getItem(key()) || 'null')
      const age = Date.now() - Number(value?.updatedAt)
      return typeof value?.name === 'string' && value.name.length <= 128 && age >= 0 && age < MAX_AGE ? value.name : ''
    } catch { return '' }
  }
  const selectedSkill = ref(read())
  watch(identity, () => { selectedSkill.value = read() })
  watch([skills, selectedSkill, () => player.value?.character_sheet], () => {
    if (player.value?.character_sheet && selectedSkill.value && !skills.value.includes(selectedSkill.value)) selectedSkill.value = ''
    try {
      if (selectedSkill.value) sessionStorage.setItem(key(), JSON.stringify({ name: selectedSkill.value, updatedAt: Date.now() }))
      else sessionStorage.removeItem(key())
    } catch { /* Draft selection is optional when browser storage is unavailable. */ }
  }, { immediate: true })
  return { skills, selectedSkill, clear: () => { selectedSkill.value = ''; try { sessionStorage.removeItem(key()) } catch { /* optional */ } } }
}
