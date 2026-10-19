export interface ProgressiveTextQueueOptions {
  onText: (text: string) => void
  onIdle: () => void
  intervalMs?: number
  maxStep?: number
}

/** Displays received text in Unicode-safe chunks without delaying control events. */
export class ProgressiveTextQueue {
  private readonly onText: (text: string) => void
  private readonly onIdle: () => void
  private readonly intervalMs: number
  private readonly maxStep: number
  private pending: string[] = []
  private stepSize = 1
  private timer: ReturnType<typeof setTimeout> | null = null
  private inputClosed = false
  private cancelled = false

  constructor(options: ProgressiveTextQueueOptions) {
    this.onText = options.onText
    this.onIdle = options.onIdle
    this.intervalMs = options.intervalMs ?? 18
    this.maxStep = options.maxStep ?? 256
  }

  push(text: string): void {
    if (this.cancelled || this.inputClosed || !text) return
    this.pending.push(...Array.from(text))
    // Give a received burst about three seconds of display time. Keep the
    // chosen pace until it drains so a long reply does not slow to a crawl.
    this.stepSize = Math.min(this.maxStep, Math.max(this.stepSize, Math.ceil(this.pending.length / 160)))
    this.schedule()
  }

  closeInput(): void {
    if (this.cancelled) return
    this.inputClosed = true
    this.schedule()
  }

  flush(): void {
    if (this.cancelled) return
    this.clearTimer()
    if (this.pending.length) {
      this.onText(this.pending.join(''))
      this.pending = []
    }
    this.stepSize = 1
    this.inputClosed = true
    this.onIdle()
  }

  resetPending(): void {
    this.pending = []
    this.stepSize = 1
    this.clearTimer()
  }

  cancel(): void {
    this.cancelled = true
    this.inputClosed = true
    this.pending = []
    this.stepSize = 1
    this.clearTimer()
  }

  private schedule(): void {
    if (this.timer !== null || !this.pending.length && !this.inputClosed) return
    if (!this.pending.length) {
      this.onIdle()
      return
    }
    this.timer = setTimeout(() => {
      this.timer = null
      const next = this.pending.splice(0, this.stepSize).join('')
      if (next) this.onText(next)
      if (this.pending.length) this.schedule()
      else {
        this.stepSize = 1
        if (this.inputClosed) this.onIdle()
      }
    }, this.intervalMs)
  }

  private clearTimer(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer)
      this.timer = null
    }
  }
}
