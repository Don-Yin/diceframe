import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApplicationFrameDecoder, encodeApplicationFrames } from '@/peer/game/framing'
import { createGameResponse, parseApplicationMessage } from '@/peer/game/protocol'
import { MultiPeerConnectionSession } from '@/peer/session/MultiPeerConnectionSession'
import { WebRtcTransport } from '@/peer/transport/WebRtcTransport'

afterEach(() => vi.unstubAllGlobals())

describe('peer application protocol', () => {
  it('rejects arbitrary RPC-like messages', () => {
    expect(() => parseApplicationMessage(JSON.stringify({
      version: 1,
      type: 'http.request',
      id: 'request-1',
      path: '/api/config',
    }))).toThrow('unsupported_application_message')

    expect(() => parseApplicationMessage(JSON.stringify({
      version: 1,
      type: 'diagnostic.text',
      id: 'diagnostic-1',
      text: 'arbitrary user text',
    }))).toThrow('unsupported_application_message')
  })

  it('fragments and reassembles a bounded large game response', () => {
    const response = createGameResponse('request-1', true, { narrative: '调查'.repeat(40_000) })
    const frames = encodeApplicationFrames(response)
    const decoder = new ApplicationFrameDecoder()
    let decoded = null
    for (const frame of frames) decoded = decoder.accept(frame) || decoded

    expect(frames.length).toBeGreaterThan(1)
    expect(decoded).toEqual(response)
  })

  it('rejects malformed transfer indexes before allocating unbounded state', () => {
    const decoder = new ApplicationFrameDecoder()
    expect(() => decoder.accept(JSON.stringify({
      version: 1,
      type: 'transfer.chunk',
      transfer_id: 'transfer-1',
      index: 99,
      total: 2,
      data: 'x',
    }))).toThrow('invalid_application_transfer')
  })

  it('rejects oversized message identifiers and conflicting duplicate chunks', () => {
    expect(() => parseApplicationMessage(JSON.stringify({
      version: 1,
      type: 'session.ping',
      id: 'x'.repeat(101),
      sent_at: Date.now(),
    }))).toThrow('invalid_application_message')

    const decoder = new ApplicationFrameDecoder()
    const chunk = {
      version: 1,
      type: 'transfer.chunk',
      transfer_id: 'transfer-1',
      index: 0,
      total: 2,
      data: 'first',
    }
    expect(decoder.accept(JSON.stringify(chunk))).toBeNull()
    expect(() => decoder.accept(JSON.stringify({ ...chunk, data: 'different' })))
      .toThrow('invalid_application_transfer')
  })
})

describe('multiplayer signaling session', () => {
  it('authenticates by peer ID and directs the host offer to one guest', async () => {
    const sent: Record<string, unknown>[] = []
    class FakeDataChannel {
      readyState = 'connecting'
      bufferedAmount = 0
      close() {}
      send() {}
    }
    class FakePeerConnection {
      connectionState: RTCPeerConnectionState = 'new'
      localDescription = { type: 'offer', sdp: 'offer-sdp', toJSON() { return this } }
      onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null
      onconnectionstatechange: (() => void) | null = null
      ondatachannel: ((event: RTCDataChannelEvent) => void) | null = null
      createDataChannel() { return new FakeDataChannel() }
      async createOffer() { return { type: 'offer', sdp: 'offer-sdp' } }
      async setLocalDescription() {}
      close() {}
    }
    class FakeWebSocket {
      static readonly OPEN = 1
      static instances: FakeWebSocket[] = []
      readyState = FakeWebSocket.OPEN
      onopen: (() => void) | null = null
      onmessage: ((event: MessageEvent<string>) => void) | null = null
      onerror: (() => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      constructor(_url: string) { FakeWebSocket.instances.push(this) }
      send(raw: string) { sent.push(JSON.parse(raw)) }
      close() {}
    }
    vi.stubGlobal('RTCPeerConnection', FakePeerConnection)
    vi.stubGlobal('WebSocket', FakeWebSocket)

    const session = new MultiPeerConnectionSession({
      isHost: true,
      localPeerId: 'h_abcdefghijk',
      token: 'host-token',
      hostPeerId: 'h_abcdefghijk',
      guestPeerIds: ['p_abcdefghijk'],
      roomCode: 'ABCDEFGH',
      websocketUrl: 'wss://api.example.test/v1/rendezvous/rooms/ABCDEFGH/ws',
      stunUrls: [],
      onState: () => undefined,
      onPeerState: () => undefined,
    })
    session.connect()
    const socket = FakeWebSocket.instances[0]
    socket.onopen?.()
    socket.onmessage?.({
      data: JSON.stringify({
        type: 'peer-ready',
        peer_id: 'p_abcdefghijk',
        is_host: false,
      }),
    } as MessageEvent<string>)
    await vi.waitFor(() => expect(sent).toHaveLength(2))

    expect(sent[0]).toEqual({
      type: 'authenticate',
      peer_id: 'h_abcdefghijk',
      token: 'host-token',
    })
    expect(sent[1]).toMatchObject({
      type: 'offer',
      target_peer_id: 'p_abcdefghijk',
      description: { type: 'offer', sdp: 'offer-sdp' },
    })
    session.close()
  })

  it('peer-left tears down a connected peer instead of leaving a dead transport', async () => {
    const sent: Record<string, unknown>[] = []
    const peerStates: Array<[string, string]> = []
    const createdPeers: unknown[] = []
    class FakeDataChannel {
      readyState = 'connecting'
      bufferedAmount = 0
      close() {}
      send() {}
    }
    class FakePeerConnection {
      connectionState: RTCPeerConnectionState = 'new'
      localDescription = { type: 'offer', sdp: 'offer-sdp', toJSON() { return this } }
      onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null
      onconnectionstatechange: (() => void) | null = null
      ondatachannel: ((event: RTCDataChannelEvent) => void) | null = null
      createDataChannel() { createdPeers.push(this); return new FakeDataChannel() }
      async createOffer() { return { type: 'offer', sdp: 'offer-sdp' } }
      async setLocalDescription() {}
      close() {}
    }
    class FakeWebSocket {
      static readonly OPEN = 1
      static instances: FakeWebSocket[] = []
      readyState = FakeWebSocket.OPEN
      onopen: (() => void) | null = null
      onmessage: ((event: MessageEvent<string>) => void) | null = null
      onerror: (() => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      constructor(_url: string) { FakeWebSocket.instances.push(this) }
      send(raw: string) { sent.push(JSON.parse(raw)) }
      close() {}
    }
    vi.stubGlobal('RTCPeerConnection', FakePeerConnection)
    vi.stubGlobal('WebSocket', FakeWebSocket)

    const session = new MultiPeerConnectionSession({
      isHost: true,
      localPeerId: 'h_abcdefghijk',
      token: 'host-token',
      hostPeerId: 'h_abcdefghijk',
      guestPeerIds: ['p_abcdefghijk'],
      roomCode: 'ABCDEFGH',
      websocketUrl: 'wss://api.example.test/v1/rendezvous/rooms/ABCDEFGH/ws',
      stunUrls: [],
      onState: () => undefined,
      onPeerState: (peerId, state) => peerStates.push([peerId, state]),
    })
    session.connect()
    const socket = FakeWebSocket.instances[0]
    socket.onopen?.()
    socket.onmessage?.({
      data: JSON.stringify({ type: 'peer-ready', peer_id: 'p_abcdefghijk', is_host: false }),
    } as MessageEvent<string>)
    await vi.waitFor(() => expect(createdPeers).toHaveLength(1))

    // 已建 transport 的对端离开：必须清理并广播 closed
    socket.onmessage?.({
      data: JSON.stringify({ type: 'peer-left', peer_id: 'p_abcdefghijk' }),
    } as MessageEvent<string>)
    await vi.waitFor(() => expect(peerStates).toContainEqual(['p_abcdefghijk', 'closed']))

    // 同一玩家重新 peer-ready：必须新建 transport（旧 bug 会复用死连接）
    socket.onmessage?.({
      data: JSON.stringify({ type: 'peer-ready', peer_id: 'p_abcdefghijk', is_host: false }),
    } as MessageEvent<string>)
    await vi.waitFor(() => expect(createdPeers).toHaveLength(2))
    session.close()
  })

  it('buffers early ICE instead of failing the session when ICE precedes the offer', async () => {
    const sent: Record<string, unknown>[] = []
    const states: Array<[string, string | undefined]> = []
    const addedCandidates: RTCIceCandidateInit[] = []
    class FakeDataChannel {
      readyState = 'connecting'
      bufferedAmount = 0
      close() {}
      send() {}
    }
    class FakePeerConnection {
      connectionState: RTCPeerConnectionState = 'new'
      remoteDescription: RTCSessionDescriptionInit | null = null
      localDescription = { type: 'answer', sdp: 'answer-sdp', toJSON() { return this } }
      onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null
      onconnectionstatechange: (() => void) | null = null
      ondatachannel: ((event: RTCDataChannelEvent) => void) | null = null
      createDataChannel() { return new FakeDataChannel() }
      async createOffer() { return { type: 'offer', sdp: 'offer-sdp' } }
      async createAnswer() { return { type: 'answer', sdp: 'answer-sdp' } }
      async setLocalDescription() {}
      async setRemoteDescription(description: RTCSessionDescriptionInit) { this.remoteDescription = description }
      async addIceCandidate(candidate: RTCIceCandidateInit) { addedCandidates.push(candidate) }
      close() {}
    }
    class FakeWebSocket {
      static readonly OPEN = 1
      static instances: FakeWebSocket[] = []
      readyState = FakeWebSocket.OPEN
      onopen: (() => void) | null = null
      onmessage: ((event: MessageEvent<string>) => void) | null = null
      onerror: (() => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      constructor(_url: string) { FakeWebSocket.instances.push(this) }
      send(raw: string) { sent.push(JSON.parse(raw)) }
      close() {}
    }
    vi.stubGlobal('RTCPeerConnection', FakePeerConnection)
    vi.stubGlobal('WebSocket', FakeWebSocket)

    const session = new MultiPeerConnectionSession({
      isHost: false,
      localPeerId: 'p_abcdefghijk',
      token: 'guest-token',
      hostPeerId: 'h_abcdefghijk',
      guestPeerIds: ['p_abcdefghijk'],
      roomCode: 'ABCDEFGH',
      websocketUrl: 'wss://api.example.test/v1/rendezvous/rooms/ABCDEFGH/ws',
      stunUrls: [],
      onState: (state, detail) => states.push([state, detail]),
      onPeerState: () => undefined,
    })
    session.connect()
    const socket = FakeWebSocket.instances[0]
    socket.onopen?.()

    // ICE 先于 offer 到达：不得终结会话（旧实现直接 fail）
    socket.onmessage?.({
      data: JSON.stringify({
        type: 'ice',
        from_peer_id: 'h_abcdefghijk',
        candidate: { candidate: 'candidate:1', sdpMid: '0' },
      }),
    } as MessageEvent<string>)
    expect(states.map(([state]) => state)).not.toContain('error')

    // offer 到达：建立 transport 并注入缓存的候选
    socket.onmessage?.({
      data: JSON.stringify({
        type: 'offer',
        from_peer_id: 'h_abcdefghijk',
        description: { type: 'offer', sdp: 'offer-sdp' },
      }),
    } as MessageEvent<string>)
    await vi.waitFor(() => {
      expect(addedCandidates).toHaveLength(1)
      expect(sent.some(item => item.type === 'answer')).toBe(true)
    })
    expect(states.map(([state]) => state)).not.toContain('error')
    session.close()
  })

  it('signals loss when the signaling socket drops but peers stay, then fails after the last peer leaves', async () => {
    const sent: Record<string, unknown>[] = []
    const states: Array<[string, string | undefined]> = []
    let channel: FakeDataChannel | null = null
    class FakeDataChannel {
      readyState = 'connecting'
      bufferedAmount = 0
      onopen: (() => void) | null = null
      onclose: (() => void) | null = null
      close() { this.readyState = 'closed' }
      send() {}
    }
    class FakePeerConnection {
      connectionState: RTCPeerConnectionState = 'new'
      localDescription = { type: 'offer', sdp: 'offer-sdp', toJSON() { return this } }
      onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null
      onconnectionstatechange: (() => void) | null = null
      ondatachannel: ((event: RTCDataChannelEvent) => void) | null = null
      createDataChannel() { channel = new FakeDataChannel(); return channel }
      async createOffer() { return { type: 'offer', sdp: 'offer-sdp' } }
      async setLocalDescription() {}
      close() {}
    }
    class FakeWebSocket {
      static readonly OPEN = 1
      static instances: FakeWebSocket[] = []
      readyState = FakeWebSocket.OPEN
      onopen: (() => void) | null = null
      onmessage: ((event: MessageEvent<string>) => void) | null = null
      onerror: (() => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      constructor(_url: string) { FakeWebSocket.instances.push(this) }
      send(raw: string) { sent.push(JSON.parse(raw)) }
      close() { this.readyState = 3 }
    }
    vi.stubGlobal('RTCPeerConnection', FakePeerConnection)
    vi.stubGlobal('WebSocket', FakeWebSocket)

    const session = new MultiPeerConnectionSession({
      isHost: true,
      localPeerId: 'h_abcdefghijk',
      token: 'host-token',
      hostPeerId: 'h_abcdefghijk',
      guestPeerIds: ['p_abcdefghijk'],
      roomCode: 'ABCDEFGH',
      websocketUrl: 'wss://api.example.test/v1/rendezvous/rooms/ABCDEFGH/ws',
      stunUrls: [],
      onState: (state, detail) => states.push([state, detail]),
      onPeerState: () => undefined,
    })
    session.connect()
    const socket = FakeWebSocket.instances[0]
    socket.onopen?.()
    socket.onmessage?.({
      data: JSON.stringify({ type: 'peer-ready', peer_id: 'p_abcdefghijk', is_host: false }),
    } as MessageEvent<string>)
    await vi.waitFor(() => expect(channel).not.toBeNull())
    channel!.readyState = 'open'
    channel!.onopen?.()

    // 信令意外断开（非 room-complete）：已有对端连接时保持 connected 并提示
    socket.readyState = 3
    socket.onclose?.({ code: 1006, reason: '' } as CloseEvent)
    expect(states.some(([state, detail]) => state === 'connected' && String(detail).startsWith('signaling_lost'))).toBe(true)

    // 最后一个对端断开后：明确失败，不再停在 waiting
    channel!.onclose?.()
    expect(states[states.length - 1]).toEqual(['error', 'signaling_lost'])
    session.close()
  })
})

describe('WebRTC transport backpressure', () => {
  it('queues a frame batch and resumes when the channel buffer drains', () => {
    class FakeDataChannel {
      readyState: RTCDataChannelState = 'connecting'
      bufferedAmount = 0
      bufferedAmountLowThreshold = 0
      sent: string[] = []
      onopen: (() => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      onerror: (() => void) | null = null
      onclose: (() => void) | null = null
      onbufferedamountlow: (() => void) | null = null
      close() { this.readyState = 'closed' }
      send(message: string) {
        this.sent.push(message)
        this.bufferedAmount += new TextEncoder().encode(message).byteLength
      }
    }
    const channel = new FakeDataChannel()
    class FakePeerConnection {
      connectionState: RTCPeerConnectionState = 'new'
      onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null
      onconnectionstatechange: (() => void) | null = null
      createDataChannel() { return channel }
      close() {}
    }
    vi.stubGlobal('RTCPeerConnection', FakePeerConnection)
    const transport = new WebRtcTransport({
      initiator: true,
      stunUrls: [],
      onIceCandidate: () => undefined,
      onIceComplete: () => undefined,
      onState: () => undefined,
      onOpen: () => undefined,
      onMessage: () => undefined,
      onClose: () => undefined,
      onError: () => undefined,
    })
    channel.readyState = 'open'
    channel.onopen?.()

    transport.sendMany(['a'.repeat(150_000), 'b'.repeat(150_000), 'c'.repeat(150_000)])
    expect(channel.sent).toHaveLength(2)
    channel.bufferedAmount = 0
    channel.onbufferedamountlow?.()
    expect(channel.sent).toHaveLength(3)
    transport.close()
  })
})
