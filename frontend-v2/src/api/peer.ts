import { i18n } from '@/i18n'
import { api } from './client'
import type {
  RendezvousConfigResponse,
  RendezvousRoomResponse,
} from './types'

export function getRendezvousConfig(): Promise<RendezvousConfigResponse> {
  return api<RendezvousConfigResponse>('/hub/rendezvous/config')
}

export function createRendezvousRoom(
  peerCount: number,
): Promise<RendezvousRoomResponse> {
  return api<unknown>('/hub/rendezvous/rooms', {
    method: 'POST',
    body: JSON.stringify({ peer_count: peerCount }),
  }).then(validateRendezvousRoom)
}

function validateRendezvousRoom(value: unknown): RendezvousRoomResponse {
  if (!value || typeof value !== 'object') {
    throw new Error(i18n.global.t('peerHubResponseInvalid'))
  }
  const room = value as Partial<RendezvousRoomResponse>
  const invitations = room.invitations
  const protocolVersion = room.protocol_version
  if (
    (
      protocolVersion !== 2
      // v3+ 是 Hub 新增协议：提示更新客户端，而非误导用户更新 Hub。
      && !(typeof protocolVersion === 'number' && protocolVersion > 2)
    )
    || room.topology !== 'host-star'
    || typeof room.room_code !== 'string'
    || typeof room.host_peer_id !== 'string'
    || typeof room.host_token !== 'string'
    || typeof room.expires_at !== 'string'
    || typeof room.websocket_url !== 'string'
    || !Array.isArray(invitations)
    || invitations.some(item => (
      !item
      || typeof item.peer_id !== 'string'
      || typeof item.token !== 'string'
    ))
  ) {
    throw new Error(i18n.global.t('peerHubProtocolIncompatible'))
  }
  if (protocolVersion !== 2) {
    throw new Error(i18n.global.t('peerClientUpdateRequired'))
  }
  return room as RendezvousRoomResponse
}
