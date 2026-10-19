import { computed, onBeforeUnmount, onMounted, ref, type CSSProperties } from 'vue'

/*
 * Geometry of the floating DF Agent window: a non-modal chat window that
 * opens next to the launcher, moves by its header and resizes from its
 * edges. Geometry is a per-browser convenience kept in localStorage; on
 * phones the window is always a full-screen sheet.
 */

export const ASSISTANT_WINDOW_STORAGE_KEY = 'diceframe_assistant_window'
const LAUNCHER_RESET_EVENT = 'diceframe-assistant-launcher-reset'

export type ResizeEdge = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'
interface Rect { x: number; y: number; width: number; height: number }

export const ASSISTANT_WINDOW_MIN = { width: 340, height: 420 }
const MARGIN = 8
const COMPACT_BREAKPOINT = 640
/** Wide enough to show the task workspace beside the transcript. */
export const ASSISTANT_WINDOW_WIDE = 760

function viewport() {
  return { width: window.innerWidth || 1280, height: window.innerHeight || 800 }
}

function defaultRect(): Rect {
  const view = viewport()
  const width = Math.min(420, view.width - MARGIN * 2)
  const height = Math.min(640, view.height - 120)
  return { x: view.width - width - 24, y: Math.max(MARGIN, view.height - height - 96), width, height }
}

function clampRect(rect: Rect): Rect {
  const view = viewport()
  const width = Math.min(Math.max(rect.width, ASSISTANT_WINDOW_MIN.width), view.width - MARGIN * 2)
  const height = Math.min(Math.max(rect.height, ASSISTANT_WINDOW_MIN.height), view.height - MARGIN * 2)
  return {
    width,
    height,
    x: Math.min(Math.max(rect.x, MARGIN), view.width - width - MARGIN),
    y: Math.min(Math.max(rect.y, MARGIN), view.height - height - MARGIN),
  }
}

function readRect(): Rect | null {
  try {
    const value = JSON.parse(localStorage.getItem(ASSISTANT_WINDOW_STORAGE_KEY) || 'null') as Partial<Rect> | null
    if (!value || ![value.x, value.y, value.width, value.height].every(Number.isFinite)) return null
    return value as Rect
  } catch {
    return null
  }
}

function saveRect(rect: Rect): void {
  try { localStorage.setItem(ASSISTANT_WINDOW_STORAGE_KEY, JSON.stringify(rect)) } catch { /* Storage is optional. */ }
}

export function resetAssistantWindow(): void {
  try { localStorage.removeItem(ASSISTANT_WINDOW_STORAGE_KEY) } catch { /* Storage is optional. */ }
}

export function useAssistantWindow() {
  const rect = ref<Rect>(clampRect(readRect() || defaultRect()))
  const compact = ref(viewport().width <= COMPACT_BREAKPOINT)
  const interacting = ref<'' | 'move' | 'resize'>('')
  let start: { pointerX: number; pointerY: number; rect: Rect; edge?: ResizeEdge } | null = null

  const wide = computed(() => !compact.value && rect.value.width >= ASSISTANT_WINDOW_WIDE)
  const style = computed<CSSProperties>(() => compact.value ? {} : {
    left: `${rect.value.x}px`,
    top: `${rect.value.y}px`,
    width: `${rect.value.width}px`,
    height: `${rect.value.height}px`,
  })

  function onMove(event: PointerEvent) {
    if (!start) return
    const dx = event.clientX - start.pointerX
    const dy = event.clientY - start.pointerY
    const base = start.rect
    if (interacting.value === 'move') {
      rect.value = clampRect({ ...base, x: base.x + dx, y: base.y + dy })
      return
    }
    const edge = start.edge || 'se'
    const next = { ...base }
    if (edge.includes('e')) next.width = base.width + dx
    if (edge.includes('s')) next.height = base.height + dy
    if (edge.includes('w')) { next.width = base.width - dx; next.x = base.x + dx }
    if (edge.includes('n')) { next.height = base.height - dy; next.y = base.y + dy }
    // Keep the opposite edge anchored when a west/north drag hits the minimum.
    if (next.width < ASSISTANT_WINDOW_MIN.width) { if (edge.includes('w')) next.x = base.x + base.width - ASSISTANT_WINDOW_MIN.width; next.width = ASSISTANT_WINDOW_MIN.width }
    if (next.height < ASSISTANT_WINDOW_MIN.height) { if (edge.includes('n')) next.y = base.y + base.height - ASSISTANT_WINDOW_MIN.height; next.height = ASSISTANT_WINDOW_MIN.height }
    rect.value = clampRect(next)
  }

  function finish() {
    if (!start) return
    start = null
    interacting.value = ''
    saveRect(rect.value)
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', finish)
    window.removeEventListener('pointercancel', finish)
  }

  function begin(event: PointerEvent, mode: 'move' | 'resize', edge?: ResizeEdge) {
    if (compact.value || event.button !== 0) return
    event.preventDefault()
    start = { pointerX: event.clientX, pointerY: event.clientY, rect: { ...rect.value }, edge }
    interacting.value = mode
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', finish)
    window.addEventListener('pointercancel', finish)
  }

  /** Header drag; ignores presses on the header's own controls. */
  function startMove(event: PointerEvent) {
    const target = event.target as HTMLElement | null
    if (target?.closest('button, a, input, textarea, select, [role="button"]')) return
    begin(event, 'move')
  }

  function startResize(event: PointerEvent, edge: ResizeEdge) {
    event.stopPropagation()
    begin(event, 'resize', edge)
  }

  function reset() {
    resetAssistantWindow()
    rect.value = clampRect(defaultRect())
  }

  function onViewportResize() {
    compact.value = viewport().width <= COMPACT_BREAKPOINT
    rect.value = clampRect(rect.value)
  }

  // "Reset launcher position" in settings also brings the window back.
  onMounted(() => {
    window.addEventListener('resize', onViewportResize)
    window.addEventListener(LAUNCHER_RESET_EVENT, reset)
  })
  onBeforeUnmount(() => {
    finish()
    window.removeEventListener('resize', onViewportResize)
    window.removeEventListener(LAUNCHER_RESET_EVENT, reset)
  })

  return { rect, style, compact, wide, interacting, startMove, startResize, reset }
}
