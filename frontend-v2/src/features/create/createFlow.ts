export type CreateStep = 1 | 2 | 3 | 4
export type CreateMode = 'template' | 'custom' | 'ai'

export const CREATE_STEP_KEYS = ['stepWorld', 'stepGameSettings', 'stepCharacters', 'stepConfirm'] as const

export type CreateStepProgressState = 'upcoming' | 'current' | 'complete'

export function createStepProgress(step: CreateStep): Array<{ number: CreateStep; key: typeof CREATE_STEP_KEYS[number]; state: CreateStepProgressState }> {
  return CREATE_STEP_KEYS.map((key, index) => {
    const number = (index + 1) as CreateStep
    return { number, key, state: number < step ? 'complete' : number === step ? 'current' : 'upcoming' }
  })
}

export interface CreateStepState {
  step: CreateStep
  seed: string
  activeRule: string
  playMode: 'free' | 'adventure' | 'gal'
  adventureReady: boolean
  mode: CreateMode
  customName: string
  aiPrompt: string
  characterNames: string[]
}

/** The restored layout selects world/rules in step 1; step 2 contains settings. */
export function canAdvanceCreateStep(state: CreateStepState): boolean {
  if (state.step === 1) {
    if (state.seed.trim()) return true
    if (!state.activeRule) return false
    if (state.mode === 'custom' && !state.customName.trim()) return false
    if (state.mode === 'ai' && !state.aiPrompt.trim()) return false
    return state.playMode !== 'adventure' || state.adventureReady
  }
  if (state.step === 2) return true
  if (state.step === 3) return state.characterNames.length > 0 && state.characterNames.every(name => name.trim())
  return true
}

export function previousCreateStep(step: CreateStep): CreateStep {
  return step > 1 ? (step - 1) as CreateStep : step
}
