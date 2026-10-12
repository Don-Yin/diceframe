interface WebRtcTransportOptions {
  initiator: boolean
  stunUrls: readonly string[]
  onIceCandidate: (candidate: RTCIceCandidateInit) => void
  onIceComplete: () => void
  onState: (state: RTCPeerConnectionState) => void
  onOpen: () => void
  onMessage: (message: string) => void
  onClose: () => void
  onError: (detail: string) => void
}

const MAX_BUFFERED_BYTES = 256 * 1024
const BUFFERED_LOW_BYTES = 64 * 1024
const MAX_OUTBOUND_PENDING_BYTES = 3 * 1024 * 1024

export class WebRtcTransport {
  private readonly peer: RTCPeerConnection
  private channel: RTCDataChannel | null = null
  private pendingCandidates: RTCIceCandidateInit[] = []
  private pendingIceComplete = false
  private sendQueue: Array<{ message: string; bytes: number }> = []
  private queuedBytes = 0
  private closed = false

  constructor(private readonly options: WebRtcTransportOptions) {
    this.peer = new RTCPeerConnection({
      iceServers: options.stunUrls.length ? [{ urls: [...options.stunUrls] }] : [],
    })
    this.peer.onicecandidate = event => {
      if (event.candidate) options.onIceCandidate(event.candidate.toJSON())
      else options.onIceComplete()
    }
    this.peer.onconnectionstatechange = () => options.onState(this.peer.connectionState)
    if (options.initiator) {
      this.bindChannel(this.peer.createDataChannel('diceframe-control', { ordered: true }))
    } else {
      this.peer.ondatachannel = event => this.bindChannel(event.channel)
    }
  }

  get isOpen(): boolean {
    return this.channel?.readyState === 'open'
  }

  async createOffer(): Promise<RTCSessionDescriptionInit> {
    const offer = await this.peer.createOffer()
    await this.peer.setLocalDescription(offer)
    if (!this.peer.localDescription) throw new Error('offer_creation_failed')
    return this.peer.localDescription.toJSON()
  }

  async acceptOffer(description: RTCSessionDescriptionInit): Promise<RTCSessionDescriptionInit> {
    await this.peer.setRemoteDescription(description)
    await this.flushCandidates()
    const answer = await this.peer.createAnswer()
    await this.peer.setLocalDescription(answer)
    if (!this.peer.localDescription) throw new Error('answer_creation_failed')
    return this.peer.localDescription.toJSON()
  }

  async acceptAnswer(description: RTCSessionDescriptionInit): Promise<void> {
    await this.peer.setRemoteDescription(description)
    await this.flushCandidates()
  }

  async addRemoteCandidate(candidate: RTCIceCandidateInit): Promise<void> {
    if (this.peer.remoteDescription) await this.peer.addIceCandidate(candidate)
    else this.pendingCandidates.push(candidate)
  }

  async completeRemoteIce(): Promise<void> {
    if (this.peer.remoteDescription) await this.peer.addIceCandidate(null)
    else this.pendingIceComplete = true
  }

  send(message: string): void {
    this.sendMany([message])
  }

  sendMany(messages: readonly string[]): void {
    if (!this.isOpen || !this.channel) throw new Error('data_channel_not_ready')
    const batch = messages.map(message => ({
      message,
      bytes: new TextEncoder().encode(message).byteLength,
    }))
    const batchBytes = batch.reduce((total, item) => total + item.bytes, 0)
    if (this.channel.bufferedAmount + this.queuedBytes + batchBytes > MAX_OUTBOUND_PENDING_BYTES) {
      throw new Error('data_channel_busy')
    }
    this.sendQueue.push(...batch)
    this.queuedBytes += batchBytes
    this.flushSendQueue()
  }

  close(): void {
    if (this.closed) return
    this.closed = true
    this.channel?.close()
    this.peer.close()
    this.channel = null
    this.pendingCandidates = []
    this.pendingIceComplete = false
    this.sendQueue = []
    this.queuedBytes = 0
  }

  private async flushCandidates(): Promise<void> {
    for (const candidate of this.pendingCandidates) await this.peer.addIceCandidate(candidate)
    this.pendingCandidates = []
    if (this.pendingIceComplete) {
      this.pendingIceComplete = false
      await this.peer.addIceCandidate(null)
    }
  }

  private bindChannel(channel: RTCDataChannel): void {
    // 覆盖前解绑旧 channel 的事件：重协商产生新 channel 时，
    // 旧 channel 迟到的事件不能继续喂给 session。
    const previous = this.channel
    if (previous) {
      previous.onopen = null
      previous.onmessage = null
      previous.onerror = null
      previous.onclose = null
    }
    this.channel = channel
    channel.bufferedAmountLowThreshold = BUFFERED_LOW_BYTES
    channel.onbufferedamountlow = () => this.flushSendQueue()
    channel.onopen = () => {
      this.flushSendQueue()
      this.options.onOpen()
    }
    channel.onmessage = event => {
      if (typeof event.data === 'string') this.options.onMessage(event.data)
    }
    channel.onerror = () => this.options.onError('data_channel_failed')
    channel.onclose = () => {
      if (!this.closed) this.options.onClose()
    }
  }

  private flushSendQueue(): void {
    const channel = this.channel
    if (!channel || channel.readyState !== 'open') return
    while (this.sendQueue.length && channel.bufferedAmount <= MAX_BUFFERED_BYTES) {
      const next = this.sendQueue.shift()
      if (!next) return
      this.queuedBytes = Math.max(0, this.queuedBytes - next.bytes)
      channel.send(next.message)
    }
  }
}
