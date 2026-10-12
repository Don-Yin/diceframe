export type PeerConnectionState =
  | 'idle'
  | 'signaling'
  | 'waiting'
  | 'connecting'
  | 'connected'
  | 'closed'
  | 'error'

export interface SignalingMessage {
  type: string
  description?: RTCSessionDescriptionInit
  candidate?: RTCIceCandidateInit
  code?: string
  message?: string
  peer_id?: string
  from_peer_id?: string
  target_peer_id?: string
  is_host?: boolean
  protocol_version?: number
}

const MAX_SIGNAL_BYTES = 64 * 1024
const SIGNAL_TYPES = new Set([
  'authenticated',
  'peer-waiting',
  'peer-ready',
  'offer',
  'answer',
  'ice',
  'ice-complete',
  'complete',
  'peer-complete',
  'room-complete',
  'peer-left',
  'error',
])

export function parseSignalingMessage(raw: string): SignalingMessage {
  if (new TextEncoder().encode(raw).byteLength > MAX_SIGNAL_BYTES) {
    throw new Error('signaling_message_too_large')
  }
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    throw new Error('invalid_signaling_message')
  }
  if (!value || typeof value !== 'object') throw new Error('invalid_signaling_message')
  const message = value as Partial<SignalingMessage>
  if (typeof message.type !== 'string' || !SIGNAL_TYPES.has(message.type)) {
    throw new Error('unsupported_signaling_message')
  }
  return message as SignalingMessage
}

export function signalingErrorDetail(message: SignalingMessage): string {
  const publicMessage = typeof message.message === 'string'
    ? message.message.trim().slice(0, 300)
    : ''
  return publicMessage || message.code || 'signaling_error'
}
