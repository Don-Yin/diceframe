import { nextTick, ref, shallowRef, watch } from 'vue'

const dismissedKey = 'diceframe:onboarding:dismissed:v1'

function readDismissed(): boolean {
  try {
    return localStorage.getItem(dismissedKey) === '1'
  } catch {
    return false
  }
}

function persistDismissed(value: boolean): void {
  try {
    localStorage.setItem(dismissedKey, value ? '1' : '0')
  } catch {
    // Closing and reopening still work for this visit when storage is blocked.
  }
}

export function useGettingStartedGuide() {
  const guideDismissed = ref(readDismissed())
  const guideCard = shallowRef<{ expand: () => void } | null>(null)
  const guideLauncher = shallowRef<HTMLButtonElement | null>(null)
  let reopenPending = false

  // The archive may still be loading when the user asks to reopen the guide.
  watch(guideCard, card => {
    if (card && reopenPending) {
      reopenPending = false
      card.expand()
    }
  }, { flush: 'post' })

  function dismissGuide(): void {
    reopenPending = false
    guideDismissed.value = true
    persistDismissed(true)
    void nextTick(() => guideLauncher.value?.focus())
  }

  function reopenGuide(): void {
    reopenPending = true
    guideDismissed.value = false
    persistDismissed(false)
    if (guideCard.value) {
      reopenPending = false
      guideCard.value.expand()
    }
  }

  return { guideDismissed, guideCard, guideLauncher, dismissGuide, reopenGuide }
}
