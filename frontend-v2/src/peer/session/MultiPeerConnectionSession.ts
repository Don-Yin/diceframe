import {
  createGameChangedEvent,
  createGameRequest,
  createGameResponse,
  createHeartbeat,
  type PeerApplicationMessage,
  type PeerGameOperation,
} from '@/peer/game/protocol'
import { ApplicationFrameDecoder, encodeApplicationFrames } from '@/peer/game/framing'
import {
  parseSignalingMessage,
  signalingErrorDetail,
  type PeerConnectionState,
} from '@/peer/protocol/signaling'
import { PeerHeartbeat } from '@/peer/session/heartbeat'
import { WebRtcTransport } from '@/peer/transport/WebRtcTransport'

export interface MultiPeerConnectionOptions {
  isHost: boolean
  localPeerId: string
  token: string
  hostPeerId: string
  guestPeerIds: readonly string[]
  roomCode: string
  websocketUrl: string
  stunUrls: readonly string[]
  onState: (state: PeerConnectionState, detail?: string) => void
  onPeerState: (peerId: string, state: PeerConnectionState, detail?: string) => void
  onGameRequest?: (
    peerId: string,
    operation: PeerGameOperation,
    payload: Record<string, unknown>,
  ) => Promise<Record<string, unknown>>
  onGameEvent?: (event: 'state.changed') => void
}

interface PendingGameRequest {
  peerId: string
  resolve: (payload: Record<string, unknown>) => void
  reject: (error: Error) => void
  timer: number
}

/** 会话级缓存的早到信令：ICE 可能先于 offer/peer-ready 到达。 */
interface PendingIceItem {
  candidate?: RTCIceCandidateInit
  complete: boolean
}

/** Hub 主动下发的致命错误（鉴权失败等）才会终结整个会话。 */
class SignalingFailure extends Error {}

const MAX_PENDING_GAME_REQUESTS = 32
const GAME_REQUEST_TIMEOUT_MS = 2 * 60 * 1000
const MAX_PENDING_ICE_PER_PEER = 64

export class MultiPeerConnectionSession {
  private socket: WebSocket | null = null
  private readonly transports = new Map<string, WebRtcTransport>()
  private readonly heartbeats = new Map<string, PeerHeartbeat>()
  private readonly frameDecoders = new Map<string, ApplicationFrameDecoder>()
  private readonly openPeers = new Set<string>()
  private readonly pendingGameRequests = new Map<string, PendingGameRequest>()
  private readonly pendingIce = new Map<string, PendingIceItem[]>()
  private signalQueue: Promise<void> = Promise.resolve()
  private closed = false
  private signalingDeliberatelyClosed = false
  private signalingLost = false

  constructor(private readonly options: MultiPeerConnectionOptions) {
    if (!options.localPeerId || !options.hostPeerId) throw new Error('invalid_peer_identity')
    if (options.isHost && options.localPeerId !== options.hostPeerId) {
      throw new Error('invalid_host_identity')
    }
    if (!options.isHost && !options.guestPeerIds.includes(options.localPeerId)) {
      throw new Error('invalid_guest_identity')
    }
  }

  get connectedPeerIds(): readonly string[] {
    return [...this.openPeers]
  }

  connect(): void {
    if (this.socket) throw new Error('session_already_started')
    this.closed = false
    this.options.onState('signaling')
    this.socket = new WebSocket(this.options.websocketUrl)
    this.socket.onopen = () => this.sendSignal({
      type: 'authenticate',
      peer_id: this.options.localPeerId,
      token: this.options.token,
    })
    this.socket.onmessage = event => {
      if (typeof event.data !== 'string') return
      this.signalQueue = this.signalQueue
        .then(() => this.handleSignal(event.data as string))
        .catch(error => {
          if (error instanceof SignalingFailure) {
            this.fail(error.message)
            return
          }
          // 单条消息异常（乱序/未知对端/非法内容）只丢弃该消息，
          // 不终结整个多玩家会话——早到 ICE 已在 pendingIce 缓存。
        })
    }
    this.socket.onerror = () => undefined
    this.socket.onclose = event => {
      this.socket = null
      if (this.closed || this.signalingDeliberatelyClosed) return
      if (this.openPeers.size > 0) {
        // 数据通道可能仍然存活：标记信令丢失并提示；最后一个对端
        // 断开时在 updateAggregateState 里转入明确失败，让 UI 走恢复路径。
        this.signalingLost = true
        this.options.onState('connected', `signaling_lost:${this.progressDetail()}`)
        return
      }
      const publicReason = event.reason.trim().slice(0, 300)
      this.fail(publicReason || (
        event.code === 1006 ? 'signaling_socket_failed' : 'signaling_socket_closed'
      ))
    }
  }

  requestGame(
    peerId: string,
    operation: PeerGameOperation,
    payload: Record<string, unknown> = {},
  ): Promise<Record<string, unknown>> {
    if (this.pendingGameRequests.size >= MAX_PENDING_GAME_REQUESTS) {
      return Promise.reject(new Error('too_many_pending_game_requests'))
    }
    const request = createGameRequest(operation, payload)
    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => {
        this.pendingGameRequests.delete(request.id)
        reject(new Error('game_request_timeout'))
      }, GAME_REQUEST_TIMEOUT_MS)
      this.pendingGameRequests.set(request.id, { peerId, resolve, reject, timer })
      try {
        this.sendApplication(peerId, request)
      } catch (error) {
        window.clearTimeout(timer)
        this.pendingGameRequests.delete(request.id)
        reject(error instanceof Error ? error : new Error('game_request_failed'))
      }
    })
  }

  notifyGameChanged(): void {
    if (!this.options.isHost) throw new Error('host_only_operation')
    const event = createGameChangedEvent()
    for (const peerId of this.openPeers) this.trySendApplication(peerId, event)
  }

  close(): void {
    if (this.closed) return
    this.closed = true
    for (const heartbeat of this.heartbeats.values()) heartbeat.stop()
    for (const transport of this.transports.values()) transport.close()
    this.socket?.close(1000)
    this.heartbeats.clear()
    for (const decoder of this.frameDecoders.values()) decoder.clear()
    this.frameDecoders.clear()
    this.transports.clear()
    this.openPeers.clear()
    this.pendingIce.clear()
    this.rejectPendingRequests('session_closed')
    this.socket = null
    this.options.onState('closed')
  }

  private async handleSignal(raw: string): Promise<void> {
    const message = parseSignalingMessage(raw)
    if (message.type === 'authenticated' || message.type === 'peer-waiting') {
      this.options.onState('waiting', this.progressDetail())
      return
    }
    if (message.type === 'peer-ready') {
      const remotePeerId = this.requiredRemotePeerId(message.peer_id)
      this.options.onPeerState(remotePeerId, 'connecting')
      this.options.onState('connecting', this.progressDetail())
      const transport = this.ensureTransport(remotePeerId, this.options.isHost)
      if (this.options.isHost) {
        const description = await transport.createOffer()
        this.sendDirectedSignal(remotePeerId, { type: 'offer', description })
      }
      return
    }
    if (message.type === 'offer' && !this.options.isHost && message.description) {
      const remotePeerId = this.requiredRemotePeerId(message.from_peer_id)
      const description = await this.ensureTransport(remotePeerId, false)
        .acceptOffer(message.description)
      this.sendDirectedSignal(remotePeerId, { type: 'answer', description })
      return
    }
    if (message.type === 'answer' && this.options.isHost && message.description) {
      const remotePeerId = this.requiredRemotePeerId(message.from_peer_id)
      await this.requiredTransport(remotePeerId).acceptAnswer(message.description)
      return
    }
    if (message.type === 'ice' && message.candidate) {
      const remotePeerId = this.requiredRemotePeerId(message.from_peer_id)
      const transport = this.transports.get(remotePeerId)
      if (!transport) {
        // ICE 先于 offer/peer-ready 到达：缓存，transport 建立后按序注入。
        this.bufferPendingIce(remotePeerId, { candidate: message.candidate, complete: false })
        return
      }
      await transport.addRemoteCandidate(message.candidate)
      return
    }
    if (message.type === 'ice-complete') {
      const remotePeerId = this.requiredRemotePeerId(message.from_peer_id)
      const transport = this.transports.get(remotePeerId)
      if (!transport) {
        this.bufferPendingIce(remotePeerId, { complete: true })
        return
      }
      await transport.completeRemoteIce()
      return
    }
    if (message.type === 'peer-left') {
      // 对端信令断开（刷新/关闭页面）：无论是否已建连都清理该对端，
      // 避免残留死 transport 被后续 peer-ready 复用导致 createOffer 失败。
      const remotePeerId = this.requiredRemotePeerId(message.peer_id)
      this.closePeer(remotePeerId, 'peer_left')
      return
    }
    if (message.type === 'error') throw new SignalingFailure(signalingErrorDetail(message))
    if (message.type === 'room-complete') {
      this.signalingDeliberatelyClosed = true
      this.socket?.close(1000)
    }
  }

  private bufferPendingIce(remotePeerId: string, item: PendingIceItem): void {
    const queue = this.pendingIce.get(remotePeerId) ?? []
    if (queue.length >= MAX_PENDING_ICE_PER_PEER) return
    queue.push(item)
    this.pendingIce.set(remotePeerId, queue)
  }

  private async flushPendingIce(remotePeerId: string, transport: WebRtcTransport): Promise<void> {
    const queue = this.pendingIce.get(remotePeerId)
    if (!queue) return
    this.pendingIce.delete(remotePeerId)
    for (const item of queue) {
      if (item.complete) await transport.completeRemoteIce()
      else if (item.candidate) await transport.addRemoteCandidate(item.candidate)
    }
  }

  private ensureTransport(remotePeerId: string, initiator: boolean): WebRtcTransport {
    const existing = this.transports.get(remotePeerId)
    if (existing) return existing
    const transport = new WebRtcTransport({
      initiator,
      stunUrls: this.options.stunUrls,
      onIceCandidate: candidate => this.sendDirectedSignal(
        remotePeerId,
        { type: 'ice', candidate },
      ),
      onIceComplete: () => this.sendDirectedSignal(remotePeerId, { type: 'ice-complete' }),
      onState: state => {
        if (state === 'failed') this.closePeer(remotePeerId, 'peer_connection_failed')
        if (state === 'disconnected' && !this.closed) {
          this.options.onPeerState(remotePeerId, 'connecting', 'peer_disconnected')
        }
      },
      onOpen: () => this.peerOpened(remotePeerId),
      onMessage: raw => this.handleApplicationMessage(remotePeerId, raw),
      onError: detail => this.closePeer(remotePeerId, detail),
      onClose: () => this.closePeer(remotePeerId, 'peer_closed'),
    })
    this.transports.set(remotePeerId, transport)
    this.frameDecoders.set(remotePeerId, new ApplicationFrameDecoder())
    void this.flushPendingIce(remotePeerId, transport).catch(() => {
      this.closePeer(remotePeerId, 'peer_ice_failed')
    })
    return transport
  }

  private peerOpened(remotePeerId: string): void {
    this.openPeers.add(remotePeerId)
    this.options.onPeerState(remotePeerId, 'connected')
    this.updateAggregateState()
    this.sendDirectedSignal(remotePeerId, { type: 'complete' })
    const heartbeat = new PeerHeartbeat({
      sendPing: sentAt => {
        if (!this.trySendApplication(remotePeerId, createHeartbeat('session.ping', sentAt))) {
          this.closePeer(remotePeerId, 'peer_heartbeat_failed')
        }
      },
      onTimeout: () => this.closePeer(remotePeerId, 'peer_heartbeat_timeout'),
    })
    this.heartbeats.set(remotePeerId, heartbeat)
    heartbeat.start()
  }

  private handleApplicationMessage(remotePeerId: string, raw: string): void {
    try {
      const message = this.frameDecoders.get(remotePeerId)?.accept(raw)
      if (!message) return
      this.heartbeats.get(remotePeerId)?.noteActivity()
      if (message.type === 'session.ping') {
        this.sendApplication(remotePeerId, createHeartbeat('session.pong', message.sent_at))
      } else if (message.type === 'game.request') {
        void this.handleGameRequest(
          remotePeerId,
          message.id,
          message.operation,
          message.payload,
        )
      } else if (message.type === 'game.response') {
        this.handleGameResponse(remotePeerId, message.request_id, message)
      } else if (message.type === 'game.event') {
        this.options.onGameEvent?.(message.event)
      }
    } catch (error) {
      this.closePeer(
        remotePeerId,
        error instanceof Error ? error.message : 'invalid_application_message',
      )
    }
  }

  private closePeer(remotePeerId: string, detail: string): void {
    const transport = this.transports.get(remotePeerId)
    this.transports.delete(remotePeerId)
    this.openPeers.delete(remotePeerId)
    this.heartbeats.get(remotePeerId)?.stop()
    this.heartbeats.delete(remotePeerId)
    this.frameDecoders.get(remotePeerId)?.clear()
    this.frameDecoders.delete(remotePeerId)
    this.pendingIce.delete(remotePeerId)
    transport?.close()
    this.rejectPendingRequests('peer_closed', remotePeerId)
    // 无 transport（对端从未建连就离开）也要广播状态，否则 store 里
    // 该对端永远停在 waiting。
    this.options.onPeerState(remotePeerId, 'closed', detail)
    if (!this.closed) this.updateAggregateState()
  }

  private updateAggregateState(): void {
    if (this.openPeers.size > 0) {
      this.options.onState(
        'connected',
        this.signalingLost ? `signaling_lost:${this.progressDetail()}` : this.progressDetail(),
      )
    } else if (this.signalingLost && !this.signalingDeliberatelyClosed) {
      // 信令已断且无存活对端：无法再建立新连接，明确失败让 UI 走恢复路径。
      this.fail('signaling_lost')
    } else {
      this.options.onState('waiting', this.progressDetail())
    }
  }

  private progressDetail(): string {
    const total = this.options.isHost ? this.options.guestPeerIds.length : 1
    return `${this.openPeers.size}/${total}`
  }

  private requiredRemotePeerId(value: string | undefined): string {
    if (!value || !this.isExpectedRemote(value)) throw new Error('unexpected_peer_id')
    return value
  }

  private isExpectedRemote(peerId: string): boolean {
    return this.options.isHost
      ? this.options.guestPeerIds.includes(peerId)
      : peerId === this.options.hostPeerId
  }

  private requiredTransport(remotePeerId: string): WebRtcTransport {
    const transport = this.transports.get(remotePeerId)
    if (!transport) throw new Error('peer_connection_missing')
    return transport
  }

  private sendDirectedSignal(peerId: string, payload: Record<string, unknown>): void {
    this.sendSignal({ ...payload, target_peer_id: peerId })
  }

  private async handleGameRequest(
    peerId: string,
    requestId: string,
    operation: PeerGameOperation,
    payload: Record<string, unknown>,
  ): Promise<void> {
    const handler = this.options.onGameRequest
    if (!this.options.isHost || !handler) {
      this.trySendApplication(
        peerId,
        createGameResponse(requestId, false, undefined, 'game_request_not_allowed'),
      )
      return
    }
    try {
      const response = await handler(peerId, operation, payload)
      if (!this.trySendApplication(peerId, createGameResponse(requestId, true, response))) {
        this.trySendApplication(
          peerId,
          createGameResponse(requestId, false, undefined, 'game_response_delivery_failed'),
        )
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'game_request_failed'
      this.trySendApplication(
        peerId,
        createGameResponse(requestId, false, undefined, detail),
      )
    }
  }

  private handleGameResponse(
    peerId: string,
    requestId: string,
    message: Extract<PeerApplicationMessage, { type: 'game.response' }>,
  ): void {
    const pending = this.pendingGameRequests.get(requestId)
    if (!pending || pending.peerId !== peerId) return
    window.clearTimeout(pending.timer)
    this.pendingGameRequests.delete(requestId)
    if (message.ok) pending.resolve(message.payload ?? {})
    else pending.reject(new Error(message.error || 'game_request_failed'))
  }

  private rejectPendingRequests(detail: string, peerId?: string): void {
    for (const [requestId, pending] of this.pendingGameRequests) {
      if (peerId && pending.peerId !== peerId) continue
      window.clearTimeout(pending.timer)
      this.pendingGameRequests.delete(requestId)
      pending.reject(new Error(detail))
    }
  }

  private sendApplication(peerId: string, message: PeerApplicationMessage): void {
    this.requiredTransport(peerId).sendMany(encodeApplicationFrames(message))
  }

  private trySendApplication(peerId: string, message: PeerApplicationMessage): boolean {
    try {
      this.sendApplication(peerId, message)
      return true
    } catch {
      return false
    }
  }

  private sendSignal(payload: Record<string, unknown>): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(payload))
  }

  private fail(detail: string): void {
    if (this.closed) return
    this.closed = true
    for (const heartbeat of this.heartbeats.values()) heartbeat.stop()
    for (const transport of this.transports.values()) transport.close()
    this.socket?.close()
    this.heartbeats.clear()
    for (const decoder of this.frameDecoders.values()) decoder.clear()
    this.frameDecoders.clear()
    this.transports.clear()
    this.openPeers.clear()
    this.pendingIce.clear()
    this.rejectPendingRequests(detail)
    this.socket = null
    this.options.onState('error', detail)
  }
}
