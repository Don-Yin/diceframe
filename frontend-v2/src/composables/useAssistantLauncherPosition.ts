import { computed, onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

export const ASSISTANT_LAUNCHER_POSITION_STORAGE_KEY = 'diceframe_assistant_launcher_position'
const RESET_EVENT = 'diceframe-assistant-launcher-reset'

export function resetAssistantLauncherPosition(): void {
  try { localStorage.removeItem(ASSISTANT_LAUNCHER_POSITION_STORAGE_KEY) } catch { /* Storage is optional. */ }
  window.dispatchEvent(new Event(RESET_EVENT))
}

type LauncherPosition = { x: number; y: number }

const DRAG_THRESHOLD = 6

function readPosition(): LauncherPosition | null {
  try {
    const raw = localStorage.getItem(ASSISTANT_LAUNCHER_POSITION_STORAGE_KEY)
    if (!raw) return null
    const value = JSON.parse(raw) as Partial<LauncherPosition>
    return Number.isFinite(value.x) && Number.isFinite(value.y)
      ? { x: value.x as number, y: value.y as number }
      : null
  } catch {
    return null
  }
}

function clamp(value: number, max: number): number {
  return Math.min(Math.max(0, value), Math.max(0, max))
}

function clampPosition(position: LauncherPosition, width = 48, height = 48): LauncherPosition {
  return {
    x: clamp(position.x, window.innerWidth - width),
    y: clamp(position.y, window.innerHeight - height),
  }
}

function savePosition(position: LauncherPosition): void {
  try {
    localStorage.setItem(ASSISTANT_LAUNCHER_POSITION_STORAGE_KEY, JSON.stringify(position))
  } catch {
    // Browser storage is optional; dragging remains effective for this session.
  }
}

export function useAssistantLauncherPosition() {
  const launcherRef = ref<HTMLElement | { $el?: HTMLElement } | null>(null)
  const position = ref<LauncherPosition | null>(readPosition())
  const dragging = ref(false)
  let suppressClick = false
  let pointerId: number | null = null
  let startPointer = { x: 0, y: 0 }
  let startPosition = { x: 0, y: 0 }
  let moved = false

  const style = computed(() => position.value ? {
    left: `${position.value.x}px`,
    top: `${position.value.y}px`,
    right: 'auto',
    bottom: 'auto',
  } : { left: 'auto', top: 'auto', right: '', bottom: '' })

  function resetPosition(): void {
    const captured = pointerId
    pointerId = null
    dragging.value = false
    suppressClick = false
    position.value = null
    const element = launcherRef.value && '$el' in launcherRef.value ? launcherRef.value.$el : launcherRef.value
    if (captured !== null && (element as HTMLElement | null)?.hasPointerCapture?.(captured)) {
      (element as HTMLElement).releasePointerCapture(captured)
    }
  }

  function syncToViewport(): void {
    if (!position.value) return
    const element = launcherRef.value && '$el' in launcherRef.value ? launcherRef.value.$el : launcherRef.value
    const rect = (element as HTMLElement | undefined)?.getBoundingClientRect?.()
    const next = clampPosition(position.value, rect?.width || 48, rect?.height || 48)
    if (next.x !== position.value.x || next.y !== position.value.y) {
      position.value = next
      savePosition(next)
    }
  }

  function onPointerDown(event: PointerEvent): void {
    if (pointerId !== null || (event.button !== 0 && event.pointerType === 'mouse')) return
    const element = event.currentTarget as HTMLElement
    const rect = element.getBoundingClientRect()
    pointerId = event.pointerId
    startPointer = { x: event.clientX, y: event.clientY }
    startPosition = position.value ?? { x: rect.left, y: rect.top }
    moved = false
    suppressClick = false
    dragging.value = false
    element.setPointerCapture?.(event.pointerId)
  }

  function onPointerMove(event: PointerEvent): void {
    if (pointerId !== event.pointerId) return
    const dx = event.clientX - startPointer.x
    const dy = event.clientY - startPointer.y
    if (!moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
    moved = true
    dragging.value = true
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
    const next = clampPosition({ x: startPosition.x + dx, y: startPosition.y + dy }, rect.width, rect.height)
    position.value = next
    savePosition(next)
    event.preventDefault()
  }

  function onPointerUp(event: PointerEvent): boolean {
    if (pointerId !== event.pointerId) return false
    const element = event.currentTarget as HTMLElement
    pointerId = null
    dragging.value = false
    suppressClick = true
    if (element.hasPointerCapture?.(event.pointerId)) element.releasePointerCapture(event.pointerId)
    return !moved
  }

  function onPointerCancel(event: PointerEvent): void {
    if (pointerId !== event.pointerId) return
    pointerId = null
    dragging.value = false
    suppressClick = true
    const element = event.currentTarget as HTMLElement
    if (element.hasPointerCapture?.(event.pointerId)) element.releasePointerCapture(event.pointerId)
  }

  function consumeClick(event: MouseEvent): boolean {
    // Pointerup handles a deliberate tap. Its compatibility click (including
    // a delayed click after dragging) must not activate again. Keyboard and
    // assistive activation have no pointerdown and use a zero-detail click.
    return event.detail !== 0 && suppressClick
  }

  onMounted(() => {
    syncToViewport()
    window.addEventListener('resize', syncToViewport)
    window.addEventListener(RESET_EVENT, resetPosition)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('resize', syncToViewport)
    window.removeEventListener(RESET_EVENT, resetPosition)
  })

  return {
    launcherRef: launcherRef as Ref<HTMLElement | { $el?: HTMLElement } | null>,
    style,
    dragging,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onPointerCancel,
    consumeClick,
  }
}
