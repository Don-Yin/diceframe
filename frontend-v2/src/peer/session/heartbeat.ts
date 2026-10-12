export const PEER_HEARTBEAT_INTERVAL_MS = 15_000
export const PEER_DISCONNECT_GRACE_MS = 45_000

interface HeartbeatOptions {
  sendPing: (sentAt: number) => void
  onTimeout: () => void
}

export class PeerHeartbeat {
  private timer: number | undefined
  private lastActivity = Date.now()

  constructor(private readonly options: HeartbeatOptions) {}

  start(): void {
    this.stop()
    this.lastActivity = Date.now()
    this.timer = window.setInterval(() => this.tick(), PEER_HEARTBEAT_INTERVAL_MS)
  }

  noteActivity(): void {
    this.lastActivity = Date.now()
  }

  stop(): void {
    if (this.timer !== undefined) window.clearInterval(this.timer)
    this.timer = undefined
  }

  private tick(): void {
    const now = Date.now()
    if (now - this.lastActivity > PEER_DISCONNECT_GRACE_MS) {
      this.stop()
      this.options.onTimeout()
      return
    }
    try {
      this.options.sendPing(now)
    } catch {
      // Temporary DataChannel backpressure is handled by the activity grace period.
    }
  }
}
